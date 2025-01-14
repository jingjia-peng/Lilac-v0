from enum import Enum

from tabulate import tabulate

from .base import InferRule, InferAPIArg, ResponseInfo, process_schema


class GoogleIDType(Enum):
    ID = 0  # 'ID' is the only schema
    BASE_CHILD = 1  # 'baseID' and 'child_{key}' separated by '/
    COMPONENT = 2  # 'component_{i}' separated by '/


class GoogleIDSchema:
    def __init__(self, id_type: GoogleIDType, tf_type: str, key=""):
        self.idtype = id_type
        self.tftype = tf_type
        if id_type == GoogleIDType.ID:
            self.key = "ID"
        elif id_type == GoogleIDType.BASE_CHILD and not key:
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


class GoogleResponseInfo(ResponseInfo):
    """
    Store information that can be infered from a cloud response
    """

    def __init__(self):
        super().__init__()

    def add_id_schema(self, schema: str, component: str, tf_type: str):
        schema = process_schema(schema)
        if component == "ID":
            self.schema_map[schema].add(GoogleIDSchema(GoogleIDType.ID, tf_type))
            self.tftypes_schemas.add(GoogleIDSchema(GoogleIDType.ID, tf_type))
        elif component == "baseID":
            self.schema_map[schema].add(
                GoogleIDSchema(GoogleIDType.BASE_CHILD, tf_type)
            )
            self.tftypes_schemas.add(GoogleIDSchema(GoogleIDType.BASE_CHILD, tf_type))
        elif component.startswith("component_"):
            self.schema_map[schema].add(
                GoogleIDSchema(GoogleIDType.COMPONENT, tf_type, component)
            )
            self.tftypes_schemas.add(
                GoogleIDSchema(GoogleIDType.COMPONENT, tf_type, component)
            )
        else:
            self.schema_map[schema].add(
                GoogleIDSchema(GoogleIDType.BASE_CHILD, tf_type, component)
            )
            self.tftypes_schemas.add(
                GoogleIDSchema(GoogleIDType.BASE_CHILD, tf_type, component)
            )

    def __str__(self) -> str:
        id_data, arg_data = [], []
        for schema, schemas in self.schema_map.items():
            for s in schemas:
                if type(s) == GoogleIDSchema:
                    id_data.append([schema, s.tftype, s.idtype, s.key])
                elif type(s) == InferAPIArg:
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


class GoogleInferRule(InferRule):
    def __init__(self):
        super().__init__(GoogleResponseInfo)
