from utils import Config
from queryRule.google import GoogleQueryRule

from .base import QueryAgent


class GoogleQueryAgent(QueryAgent):
    def __init__(self):
        super().__init__()
        self.project = Config["project"]
        if self.project is None:
            raise ValueError("Google project not set in global-config.yml")
        self.region = Config["region"]
        if self.region is None:
            raise ValueError("Google region not set in global-config.yml")
        self.cloud_type = "Google"

    def add_tools(self, cmds: list, cmd_tool_dict: dict, category: str):
        super().add_tools(cmds, cmd_tool_dict, "gcloud " + category)

    def main_loop(self, tf_type: str, target_id: str):
        self.query_chain = GoogleQueryRule(tf_type, target_id)
        id_schema = self.query_chain.get_query_IDschema(self.project)
        return super().main_loop(
            tf_type=tf_type,
            target_id=target_id,
            query_chain=self.query_chain,
            id_schema=id_schema,
            res_cnst_msg=f"in my project {
                self.project} in region {self.region}",
        )

    def get_api_call_list(self, tool_calls: list):
        api_call_list = []
        raw_api_list = []
        for tool_call in tool_calls:
            cmd = self.tool_perfix + tool_call["type"].replace("_", " ")
            raw_api_list.append(cmd)
            for k, v in tool_call["args"].items():
                # distinguish between positional arguments and flags
                raise NotImplementedError
            cmd += " --format json"
            api_call_list.append(cmd)
        return api_call_list, raw_api_list

    def retrieve_id(self, gpt_response: dict, target_id: str):
        response_list = gpt_response["chat"].split("\n")
        for id in response_list:
            # some imported ID should start with {project} but Terraform state ID does not
            if id == target_id or (id == self.project + "/" + target_id):
                return id
        return None

    def import_content(self, tf_type: str, id: str):
        return f"""provider "google" {{
    project = "{self.project}"
    region = "{self.region}"
}}
import {{
    id = "{id}"
    to = {tf_type}.example
}}
"""
