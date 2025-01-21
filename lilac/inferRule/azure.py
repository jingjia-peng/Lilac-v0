from enum import Enum

from tabulate import tabulate

from .base import InferRule, InferAPIArg, ResponseInfo, process_schema


class AzureIDType(Enum):
    ID = 0  # 'ID' is the only schema
    COMPONENT = 1  # '|' separated components as 'component_{i}
    BASE_CHILD = 2  # 'baseID' and 'child_{key}'


class AzureIDSchema:
    def __init__(self, id_type: AzureIDType, tf_type: str, key=""):
        self.idtype = id_type
        self.tftype = tf_type
        if id_type == AzureIDType.ID:
            self.key = "ID"
        elif id_type == AzureIDType.BASE_CHILD and not key:
            self.key = "baseID"
        else:
            self.key = key

    def __eq__(self, other) -> bool:
        return (
            self.tftype == other.tftype
            and self.idtype == other.idtype
            and self.key == other.key
        )

    def __hash__(self) -> int:
        return hash((self.tftype, self.idtype, self.key))


class AzureResponseInfo(ResponseInfo):
    """
    Store information that can be infered from a cloud response
    """

    def __init__(self):
        super().__init__()

    def add_id_schema(self, schema: str, component: str, tf_type: str):
        schema = process_schema(schema)
        if component == "ID":
            self.schema_map[schema].add(AzureIDSchema(AzureIDType.ID, tf_type))
            self.tftypes_schemas.add(AzureIDSchema(AzureIDType.ID, tf_type))
        elif component.startswith("component_"):
            self.schema_map[schema].add(
                AzureIDSchema(AzureIDType.COMPONENT, tf_type, component)
            )
            self.tftypes_schemas.add(
                AzureIDSchema(AzureIDType.COMPONENT, tf_type, component)
            )
        elif component == "baseID":
            self.schema_map[schema].add(AzureIDSchema(AzureIDType.BASE_CHILD, tf_type))
            self.tftypes_schemas.add(AzureIDSchema(AzureIDType.BASE_CHILD, tf_type))
        else:
            self.schema_map[schema].add(
                AzureIDSchema(AzureIDType.BASE_CHILD, tf_type, component)
            )
            self.tftypes_schemas.add(
                AzureIDSchema(AzureIDType.BASE_CHILD, tf_type, component)
            )

    def __str__(self) -> str:
        id_data, arg_data = [], []
        for schema, schemas in self.schema_map.items():
            for s in schemas:
                if type(s) == AzureIDSchema:
                    id_data.append([schema, s.tftype, s.idtype, s.key])
                elif type(s) == InferAPIArg and s.arg_name != "resource-group":
                    arg_data.append([schema, s.api_call, s.arg_name])
        ret = ""
        # print ID schemas
        if id_data:
            ret += tabulate(
                id_data,
                headers=["Schema", "Infer TF Type", "ID Type", "Key"],
                tablefmt="pretty",
            )
        # print API arg schemas
        if arg_data:
            ret += "\n\n"
            ret += tabulate(
                arg_data,
                headers=["Schema", "Infer API Call", "Arg Name"],
                tablefmt="pretty",
            )
        return ret


class AzureInferRule(InferRule):
    def __init__(self):
        super().__init__(AzureResponseInfo)
