from pathlib import Path

from pyshacl import validate
import httpx

from config import *


def main():
    # get the validator
    r = httpx.get(
        "https://raw.githubusercontent.com/surroundaustralia/ogcldapi-profile/master/validator.shacl.ttl",
        follow_redirects=True,
    )

    assert r.status_code == 200

    # for all datasets...
    warning_datasets = {}  # format {dataset_filename: warning_msg}
    invalid_datasets = {}  # format {dataset_filename: error_msg}
    datasets_dir = Path(__file__).parent.parent / "data"
    for f in datasets_dir.glob("**/*"):
        # ...validate each file
        if f.name.endswith(".ttl"):
            try:
                v = validate(str(f), shacl_graph=r.text, shacl_graph_format="ttl")
                if not v[0]:
                    if "Severity: sh:Violation" in v[2]:
                        invalid_datasets[f.name] = v[2]
                    elif "Severity: sh:Warning" in v[2]:
                        warning_datasets[f.name] = v[2]

            # syntax errors crash the validate() function
            except Exception as e:
                invalid_datasets[f.name] = e

    # check to see if we have any invalid datasets
    if len(warning_datasets.keys()) > 0 and SHOW_WARNINGS:
        print("Warning datasets:\n")
        for dataset, warning in warning_datasets.items():
            print(f"- {dataset}:")
            print(warning)
            print("-----")

    # check to see if we have any invalid datasets
    if len(invalid_datasets.keys()) > 0:
        print("Invalid datasets:\n")
        for dataset, error in invalid_datasets.items():
            print(f"- {dataset}:")
            print(error)
            print("-----")

    if WARNINGS_INVALID:
        assert len(warning_datasets.keys()) == 0, "Warning datasets: {}".format(
            ", ".join([str(x) for x in warning_datasets.keys()])
        )
    assert len(invalid_datasets.keys()) == 0, "Invalid datasets: {}".format(
        ", ".join([str(x) for x in invalid_datasets.keys()])
    )


if __name__ == "__main__":
    main()
