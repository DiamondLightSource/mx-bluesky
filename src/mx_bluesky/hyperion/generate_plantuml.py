from inspect import get_annotations, getmro, isclass
from typing import get_type_hints

from blueapi.core.bluesky_types import is_bluesky_plan_generator
from blueapi.core.context import load_module_all
from pydantic import BaseModel

from mx_bluesky.common.parameters.components import MxBlueskyParameters
from mx_bluesky.hyperion import experiment_plans


def main():
    """Build a PlantUML diagram of the parameter models"""
    print("""
'This file is auto-generated
@startuml hyperion_parameter_model
title Hyperion Parameter Model
""")

    parameter_types = [
        get_type_hints(obj)["parameters"]
        for obj in load_module_all(experiment_plans)
        if is_bluesky_plan_generator(obj)
    ]
    experiment_types = set()
    all_types = set()
    for parameter_type in parameter_types:
        experiment_types.add(parameter_type)
        all_types.add(parameter_type)

    for experiment_type in experiment_types:
        for base in getmro(experiment_type):
            if issubclass(base, BaseModel) and base is not BaseModel:
                all_types.add(base)

    mx_bluesky_param_types = set()
    print("package Mx_Bluesky_Parameters {")
    print("package Experiments {")
    for t in experiment_types:
        generate_class(t)
    print("}")
    for t in all_types:
        if issubclass(t, MxBlueskyParameters) and t not in experiment_types:
            generate_class(t)
            mx_bluesky_param_types.add(t)
    print("}")

    for t in all_types:
        if t not in experiment_types and t not in mx_bluesky_param_types:
            generate_class(t)

    for t in all_types:
        for base in t.__bases__:
            if base is not object and base is not BaseModel:
                print(f"{base.__name__} <|-- {t.__name__}")

    print("@enduml")


def generate_class(t):
    print(f"class {t.__name__}" "{")
    for field_name, field_type in get_annotations(t).items():
        print(f"\t{generate_type(field_type)} {field_name}")
    print("}")


def generate_type(field_type):
    return (
        field_type.__name__
        if isclass(field_type) and issubclass(field_type, BaseModel)
        else str(field_type)
    )


if __name__ == "__main__":
    main()
