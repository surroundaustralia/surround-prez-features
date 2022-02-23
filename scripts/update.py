from typing import List, Dict, Tuple
from pathlib import Path
import uuid

from rdflib import Dataset, Graph, URIRef, Namespace
from rdflib.namespace import RDF, RDFS, DCTERMS, DCAT
from rdflib.compare import isomorphic, to_isomorphic

from config import *
from sparql_utils import *

GEO = Namespace("http://www.opengis.net/ont/geosparql#")


def get_remote_datasets() -> List[str]:
    """Gets all datasets in the triplestore"""
    datasets = []
    results = sparql_query(
        """
        SELECT DISTINCT ?g
        WHERE {
            GRAPH ?g {
                ?s ?p ?o .
            }
            FILTER (!STRSTARTS(STR(?g), "system") && STR(?g) != "background:")
        }
    """
    )

    for result in results:
        datasets.append(result["g"]["value"])
    return datasets


def get_graph_uri_for_dataset(dataset: Path) -> URIRef:
    """We can get the Graph URI for a dataset from the dataset file as we know that
    there is only one Dataset per file"""
    g = Graph().parse(str(dataset), format="ttl")
    for s in g.subjects(predicate=RDF.type, object=DCAT.Dataset):
        return s


def get_local_datasets() -> Dict:
    """Gets all datasets in the local `data/` directory"""
    datasets = {}
    for f in Path(__file__).parent.parent.glob("data/**/*.ttl"):
        datasets[str(get_graph_uri_for_dataset(f))] = f

    return datasets


def get_diff(
    local_datasets_list: List[str], remote_datasets: List[str]
) -> Tuple[List[str]]:
    """Gets the difference between the local datasets and the triplestore datasets"""
    to_be_added = list(set(local_datasets_list) - set(remote_datasets))
    to_be_deleted = list(set(remote_datasets) - set(local_datasets_list))
    return (to_be_added, to_be_deleted)


def add_datasets(datasets: List[str], local_datasets: Dict[str, str]):
    """Adds the datasets flagged for insertion and re-adds all datasets
    to the default union graph."""

    # add dataset to triplestore
    for dataset in datasets:
        add_graph(dataset, local_datasets[dataset])

    # add all local graphs to default
    # for dataset in list(local_datasets.keys()):
    #     add_to_default(dataset)


def delete_datasets(datasets: List[str]):
    """Drops the default union graph from the triplestore and
    deletes datasets flagged for deletion."""

    # drop default graph
    # sparql_update("DROP DEFAULT")

    # drop dataset
    for dataset in datasets:
        drop_graph(dataset)


def add_graph(graph_uri: str, graph_file: Path) -> None:
    """Adds a graph to the triplestore"""
    d = Dataset()
    content_graph = d.graph(identifier=graph_uri)
    content_graph.parse(graph_file)

    # check for ID, error if has id but not unique
    r = content_graph.query(
        f"""
        PREFIX dcterms: <{DCTERMS}>
        SELECT ?id
        WHERE {{
            <{graph_uri}> dcterms:identifier ?id .
        }}
    """
    )
    if r.bindings:
        id = str(r.bindings[0]["id"])
        for key, value in id_dict.items():
            if value == id and key != graph_uri:
                raise Exception("Provided ID is not unique")

    # create system graph with inference
    system_graph = create_system_graph(graph_uri, content_graph, d)

    # add seeAlso triple to triplestore
    sparql_update(
        f"""
        PREFIX rdfs: <{RDFS}>
        INSERT DATA {{
            GRAPH <system:> {{
                <{graph_uri}> rdfs:seeAlso <{system_graph.identifier}> .
            }}
        }}
    """
    )

    # add system graph to triplestore
    sparql_insert_graph(
        system_graph.identifier, system_graph.serialize(format="turtle")
    )

    # add graph to triplestore
    with open(graph_file, "rb") as f:
        graph_content = f.read()
    sparql_insert_graph(graph_uri, graph_content)

    # update seeAlso dict
    mapping_dict[graph_uri] = str(system_graph.identifier)


def create_id(content_graph: Graph, system_graph: Graph, uri: str) -> str:
    """Creates an ID if doesn't exist & checks for uniqueness"""
    # either get ID or generate one if none exists
    r = content_graph.query(
        f"""
        PREFIX dcterms: <{DCTERMS}>
        CONSTRUCT {{
            ?c dcterms:identifier ?id .
        }}
        WHERE {{
            BIND (<{uri}> as ?c)
            OPTIONAL {{
                ?c dcterms:identifier ?given_id .
            }}
            BIND (REPLACE(STR(?c), ".*[/|#|:](.*)$", "$1") AS ?uri_id)
            BIND (COALESCE(?given_id, ?uri_id) AS ?id)
        }}
    """
    )

    # get generated id as variable
    r2 = r.graph.query(
        f"""
        PREFIX dcterms: <{DCTERMS}>
        SELECT ?id
        WHERE {{
            ?c dcterms:identifier ?id .
        }}
    """
    )
    id = r2.bindings[0]["id"]

    # check for uniqueness, retry once by adding a "1" to the id
    retries = 0
    while retries < 2:
        # check that ID is unique
        if id not in id_dict.values():
            break

        retries += 1
        if retries == 2:
            raise Exception(f"Unable to generate unique ID for {uri}")
        id += 1

    # add ID to system graph
    system_graph.add((URIRef(uri), DCTERMS.identifier, id))

    # update ID dict
    id_dict[uri] = id

    return id


def create_system_graph(
    graph_uri: str, content_graph: Graph, dataset: Dataset
) -> Graph:
    """Creates a system graph for a content graph and populates it with inferred data"""
    system_graph = dataset.graph(identifier=f"system:{uuid.uuid4()}")

    # generate IDs for datasets, feature collections & features
    r = content_graph.query(
        f"""
        PREFIX dcat: <{DCAT}>
        PREFIX geo: <{GEO}>
        SELECT ?s
        WHERE {{
            ?s a ?o .
            FILTER (?o IN (dcat:Dataset, geo:FeatureCollection, geo:Feature)) .
        }}
    """
    )
    for binding in r.bindings:
        s_id = create_id(content_graph, system_graph, binding["s"])

    # create titles for features

    # insert rdfs:member where dcterms:isPartOf & vice-versa
    dataset.update(
        f"""
        PREFIX dcterms: <{DCTERMS}>
        PREFIX geo: <{GEO}>
        PREFIX rdfs: <{RDFS}>
        INSERT {{
            GRAPH <{system_graph.identifier}> {{
                ?fc_a rdfs:member ?f_a .
                ?f_b dcterms:isPartOf ?fc_b .
            }}
        }}
        WHERE {{
            GRAPH <{graph_uri}> {{
                OPTIONAL {{
                    ?f_a a geo:Feature ;
                        dcterms:isPartOf ?fc_a .
                    ?fc_a a geo:FeatureCollection .
                }}
                OPTIONAL {{
                    ?fc_b a geo:FeatureCollection ;
                        rdfs:member ?f_b .
                    ?f_b a geo:Feature .
                }}
            }}
        }}
    """
    )

    return system_graph


def add_to_default(graph_uri: str) -> None:
    """Adds a graph to the triplestore's default union graph"""
    sparql_update(f"ADD <{graph_uri}> TO DEFAULT")
    sparql_update(f"ADD <{mapping_dict[graph_uri]}> TO DEFAULT")


def drop_graph(graph_uri: str) -> None:
    """Drops a graph from the triplestore"""
    # delete seeAlso records
    sparql_update(
        f"""
        WITH <system:>
        DELETE {{
            <{graph_uri}> ?p ?o .
        }}
        WHERE {{
            <{graph_uri}> ?p ?o .
        }}
    """
    )
    sparql_update(f"DROP GRAPH <{mapping_dict[graph_uri]}>")
    sparql_update(f"DROP GRAPH <{graph_uri}>")

    # remove from seeAlso & ID dicts
    mapping_dict.pop(graph_uri)
    id_dict.pop(graph_uri)


def get_modified_datasets(local_datasets: Dict[str, str]) -> List[str]:
    """Gets a list of the graphs that have been modified"""
    modified = []
    for uri, filename in local_datasets.items():
        # compare remote vs local graphs
        r = sparql_construct(
            f"""
            CONSTRUCT {{
                ?s ?p ?o .
            }}
            WHERE {{
                GRAPH <{uri}> {{
                    ?s ?p ?o .
                }}
            }}
        """
        )
        g_remote = Graph().parse(data=r, format="turtle")
        if len(g_remote) == 0:  # remote dataset doesn't exist
            continue

        # accounts for bnodes
        g_remote_str = to_isomorphic(g_remote).serialize(format="turtle")
        # re-parsed as namespace order is not guaranteed
        remote = Graph().parse(data=g_remote_str, format="turtle")

        with open(filename, "rb") as f:
            g_local = Graph().parse(f.read(), format="turtle")
        # accounts for bnodes
        g_local_str = to_isomorphic(g_local).serialize(format="turtle")
        # tags that get omitted in remote version
        g_local_str = g_local_str.replace("@en", "")
        g_local_str = g_local_str.replace("^^xsd:string", "")
        # re-parsed as namespace order is not guaranteed
        local = Graph().parse(data=g_local_str, format="turtle")

        # compare graphs are equal
        if not isomorphic(remote, local):
            modified.append(uri)
    return modified


if __name__ == "__main__":
    if DROP_ON_START:
        sparql_update("DROP ALL")
        sparql_update("CREATE GRAPH <system:>")
        sparql_update("CREATE GRAPH <background:>")

        # add ontology files to <background:> graph
        for ont_file in Path(__file__).parent.parent.glob("ontologies/**/*.ttl"):
            with open(ont_file, "rb") as f:
                sparql_insert_graph("background:", f.read())

    # query DB for content graph to system graph map, store in python dict
    r = sparql_query(
        f"""
        PREFIX rdfs: <{RDFS}>
        SELECT ?content ?system
        WHERE {{
            GRAPH <system:> {{
                ?content rdfs:seeAlso ?system .
            }}
        }}
    """
    )
    mapping_dict = {
        result["content"]["value"]: result["system"]["value"] for result in r
    }

    # query DB for all IDs, store in dict for uniqueness checking
    r = sparql_query(
        f"""
        PREFIX dcterms: <{DCTERMS}>
        SELECT ?content ?id
        WHERE {{
            ?content dcterms:identifier ?id .
        }}
    """
    )
    id_dict = {result["content"]["value"]: result["id"]["value"] for result in r}

    # check if id dict has distinct values
    assert len(set(id_dict.values())) == len(id_dict.values()), "Found duplicate IDs"

    # gets remote & local datasets
    remote_datasets = get_remote_datasets()
    print(f"remote datasets: {remote_datasets}")
    local_datasets = get_local_datasets()  # {uri: file, ...}
    local_datasets_list = list(local_datasets.keys())
    print(f"local datasets: {local_datasets_list}")

    modified_datasets = get_modified_datasets(local_datasets)
    print(f"modified datasets: {modified_datasets}")
    to_be_added, to_be_deleted = get_diff(local_datasets_list, remote_datasets)
    print(f"added datasets: {to_be_added}")
    print(f"removed datasets: {to_be_deleted}")

    # make changes
    delete_datasets(to_be_deleted + modified_datasets)
    add_datasets(modified_datasets + to_be_added, local_datasets)

    # output the changes
    print("added:")
    [print(f" - {dataset}") for dataset in to_be_added] if to_be_added else print(
        " None"
    )
    print("deleted:")
    [print(f" - {dataset}") for dataset in to_be_deleted] if to_be_deleted else print(
        " None"
    )
    print("modified:")
    [
        print(f" - {dataset}") for dataset in modified_datasets
    ] if modified_datasets else print(" None")
