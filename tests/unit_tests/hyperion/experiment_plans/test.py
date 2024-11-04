# import json

# from pydantic import ValidationError

# from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect

# with open(
#     "tests/test_data/parameter_json_files/good_test_load_centre_collect_params.json"
# ) as f:
#     params = json.loads(f.read())
# try:
#     thing = LoadCentreCollect(**params)
# except ValidationError as er:
#     for e in er.errors():
#         print(f"Field: {e['loc']}, Error: {e['msg']}")
