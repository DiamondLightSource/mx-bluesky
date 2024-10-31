# import json

# from pydantic import ValidationError

# from mx_bluesky.hyperion.parameters.gridscan import ThreeDGridScan


# def raw_params_from_file(filename):
#     with open(filename) as f:
#         return json.loads(f.read())


# dummy_params_1 = raw_params_from_file(
#     "tests/test_data/parameter_json_files/good_test_robot_load_parameters.json"
# )

# try:
#     dummy_params_1 = ThreeDGridScan(**dummy_params_1)
# except ValidationError as e:
#     # Print or inspect all the errors in detail
#     print("Validation Errors:")
#     for error in e.errors():
#         print(f"Field: {error['loc']}, Error: {error['msg']}")
