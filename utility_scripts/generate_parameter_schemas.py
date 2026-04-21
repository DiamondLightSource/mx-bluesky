import json
from argparse import ArgumentParser
from pathlib import Path


def main():
    parser = ArgumentParser()
    parser.add_argument("input_file")
    parser.add_argument("output_dir")
    args = parser.parse_args()

    with open(args.input_file) as stream:
        json_str = stream.read()
        json_blob = json.loads(json_str)

        for plan_dict in json_blob["plans"]:
            name = plan_dict["name"]
            schema_blob = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "description": plan_dict["description"].strip(),
                **plan_dict["schema"],
            }
            output_path = Path(args.output_dir + "/" + name + ".json")
            with open(output_path, "w") as output_stream:
                output_stream.write(json.dumps(schema_blob))


if __name__ == "__main__":
    main()
