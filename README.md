# SURROUND Prez Features
This contains the pipeline scripts for validating & updating spatial data in [Prez](https://github.com/surroundaustralia/Prez). These scripts will be run automatically in GitHub actions.

## Installing
Install using Poetry (optional), which you can install [here](https://python-poetry.org/docs/#installation) (recommended), or by running:

```bash
pip install poetry 
```

Then run `poetry install` in the root directory.

Otherwise install using `pip` as normal:

```bash
pip install -r requirements.txt 
```

## Configuration
`scripts/config.py` contains the necessary configuration.

Key|Description
-|-
DB_TYPE|Specifies the triplestore to send data to. Available options are: "fuseki", "graphdb"
DB_BASE_URI|The URI of the triplestore repository/dataset. Can be set as an environment variable.
DB_USERNAME|The username of the targeted triplestore. Required if the triplestore requires authentication. Can be set as an environment variable.
DB_PASSWORD|The password of the targeted triplestore. Required if the triplestore requires authentication. Can be set as an environment variable.
SHOW_WARNINGS|Shows validation warning messages if true
WARNINGS_INVALID|Treats validation warnings as errors if true
DROP_ON_START|When true, drops all graphs in the triplestore repository/dataset before uploading data from this repo

The SPARQL credentials (`DB_BASE_URI` (required), `DB_USERNAME` & `DB_PASSWORD`) should be set as repository secrets.

## Usage
Spatial datasets should be placed in the `data/` folder. For predicates to display properly in SpacePrez, you can provide the ontologies for those predicates in the `ontologies/` folder. A few ontologies have been provided.

SpacePrez expects one dataset per `*.ttl` file, and all related feature collections & features are contained in that same file.

### Enabling the default union graph
Ensure the targeted triplestore repository/dataset has the default union graph enabled for SpacePrez to function properly. In GraphDB this is enabled by default. For Jena-Fuseki, this setting can be enabled per dataset by adding the following line (in bold) to the configuration file for that dataset (in `/fuseki/configuration/<dataset>.ttl`):

<pre>
:tdb_dataset_readwrite
    a tdb2:DatasetTDB2 ;
    tdb2:location "/fuseki/databases/&lt;dataset&gt;" ;
    <b>tdb2:unionDefaultGraph true .</b>
</pre>

## Validation
The validation script `scripts/validate.py` uses [pySHACL](https://github.com/RDFLib/pySHACL) to ensure that each dataset, feature collection & feature conforms to the [OGC LD API profile](https://github.com/surroundaustralia/ogcldapi-profile) spec.

## Updating Data
The update script `scripts/update.py` does the following steps:

1. Checks what datasets have been added, modified & deleted
2. Each graph has a system graph created for it to insert extra data
3. As Prez requires `dcterms:identifier` for each dataset, feature collection & feature, the script creates one if it doesn't exist and inserts into the system graph
4. Fills out `rdfs:member`/`dcterms:isPartOf` two-way relations
5. Pushes the changes to the triplestore

## GitHub Actions
The standard workflow for updating data is as follows:

1. Create a pull request containing the requested changes
2. Datasets will be validated in GitHub actions
3. If validation succeeded, the pull request can be approved and merged
4. When the pull request is merged, the datasets will be uploaded to the specified triplestore
