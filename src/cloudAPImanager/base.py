import os
import json
from copy import deepcopy

import yaml
from tqdm import tqdm
from langchain_openai import AzureChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import TextLoader

from utils import Config, print_info


class CloudAPIManager:
    def __init__(self) -> None:
        self.GPT_TOOL_LIMIT = Config["GPT_TOOL_LIMIT"]
        self.agent = (
            AzureChatOpenAI(
                model=Config["model"],
                api_key=Config["api_key"],
                azure_endpoint=Config["azure_endpoint"],
                api_version=Config["api_version"],
                organization=Config["organization"],
            )
            | StrOutputParser()
        )
        self.vectorstore = None

        self.category_docs = {}
        self.cmd_dict = {}
        self.cmd_by_category = {}

    def load_api_docs(
        self,
        root_dir: str,
        filter_list: list,
        cmd_prefix: str,
        api_tree_file: str,
        api_tree_merged_file: str,
        dump: bool,
    ):
        self.__load_api_yml_docs(
            root_dir=root_dir, filter_list=filter_list, cmd_prefix=cmd_prefix
        )
        self.__build_cmd_tree(apitree_file=api_tree_file, dump=dump)
        self.__merge_cmds_by_category(
            apitree_merged_file=api_tree_merged_file, dump=dump
        )
        self.__dump_cleaned_api_docs(clean_dir=root_dir + "-cleaned")

    def __load_api_yml_docs(self, root_dir, filter_list, cmd_prefix):
        yml_files = [
            os.path.join(dp, f)
            for dp, dn, fn in os.walk(os.path.expanduser(root_dir))
            for f in fn
        ]

        for file in tqdm(yml_files, desc="Loading API docs from " + root_dir):
            with open(file, "r") as f:
                content = f.read()
            content = content.replace("\t", "  ")  # avoid yaml load error
            data = yaml.safe_load(content)

            if "name" in data:
                self.category_docs[data["name"][len(cmd_prefix) :]] = (
                    data["summary"] if "summary" in data else ""
                )

            if "directCommands" in data:
                for cmd in data["directCommands"]:
                    # only keep list/get/show commands
                    if all(s not in cmd["name"] for s in filter_list):
                        continue

                    cmd_info = {"name": cmd["name"], "summary": cmd["summary"]}

                    if "requiredParameters" in cmd:
                        cmd_info["requiredParameters"] = {}
                        req_args = cmd["requiredParameters"]
                        for req_arg in req_args:
                            cmd_info["requiredParameters"][req_arg["name"]] = {
                                "summary": req_arg["summary"]
                            }

                    self.cmd_dict[cmd["name"][len(cmd_prefix) :]] = cmd_info

        print_info(f"Loaded {len(self.cmd_dict)} query APIs from {root_dir}")

    def __build_cmd_tree(self, apitree_file, dump=False):
        for cmd in self.cmd_dict.keys():
            cmd_parts = cmd.split(" ")
            current_level = self.cmd_by_category
            for i, part in enumerate(cmd_parts):
                if i == len(cmd_parts) - 1:
                    current_level["cmd"].append(" ".join(cmd_parts))
                else:
                    if part not in current_level:
                        current_level[part] = {"cmd": []}
                    current_level = current_level[part]

        if dump:
            with open(apitree_file, "w") as f:
                yaml.dump(self.cmd_by_category, f)
            print_info("Built API tree and cached at " + apitree_file)
        else:
            print_info("Built API tree without caching")

    def __merge_cmds_by_category(self, apitree_merged_file, dump=False):
        cmd_tree = self.__merge_helper(deepcopy(self.cmd_by_category))
        self.cmd_by_category = deepcopy(cmd_tree)

        for key in list(cmd_tree.keys()):
            if len(cmd_tree[key]) > 1:
                for subkey in list(cmd_tree[key].keys()):
                    if subkey == "cmd":
                        continue
                    self.cmd_by_category[key + " " + subkey] = cmd_tree[key][subkey][
                        "cmd"
                    ]
                    self.cmd_by_category[key].pop(subkey)
                if self.cmd_by_category[key] == []:
                    self.cmd_by_category.pop(key)
            self.cmd_by_category[key] = cmd_tree[key]["cmd"]

        if dump:
            with open(apitree_merged_file, "w") as f:
                yaml.dump(self.cmd_by_category, f)
            print_info(
                f"Merged API tree with {len(self.cmd_by_category)} categories and cached at {apitree_merged_file}"
            )
        else:
            print_info(
                f"Merged API tree with {len(self.cmd_by_category)} categories without caching"
            )

    def __merge_helper(self, cmd_tree: dict):
        for key in cmd_tree:
            if key == "cmd":
                continue
            cmd_tree[key] = self.__merge_child(cmd_tree[key])
            if len(cmd_tree[key]) > 1:
                self.__merge_helper(cmd_tree[key])
        return cmd_tree

    def __merge_child(self, node: dict):
        cnt = len(node["cmd"])
        cmd = deepcopy(node["cmd"])
        for key in node:
            if key == "cmd":
                continue
            curcnt, curcmd = self.__get_child_data(node[key])
            cnt += curcnt
            cmd += curcmd

        # merge
        if cnt <= self.GPT_TOOL_LIMIT:
            return {"cmd": cmd}
        return node

    def __get_child_data(self, node: dict):
        cnt = len(node["cmd"])
        cmd = deepcopy(node["cmd"])
        for key in node:
            if key != "cmd":
                curcnt, curcmd = self.__get_child_data(node[key])
                cnt += curcnt
                cmd += curcmd
        return cnt, cmd

    def __dump_cleaned_api_docs(self, clean_dir):
        vsfiles = []
        for category, cmds in self.cmd_by_category.items():
            cmds_info = {
                "category": category,
                "summary": (
                    self.category_docs[category]
                    if category in self.category_docs
                    else ""
                ),
                "directCommands": [],
            }
            for cmd in cmds:
                cmds_info["directCommands"].append(self.cmd_dict[cmd])

            os.mkdir(clean_dir) if not os.path.exists(clean_dir) else None
            file = os.path.join(clean_dir, category + ".yml")
            with open(file, "w") as f:
                yaml.dump(cmds_info, f)
            vsfiles.extend(TextLoader(file).load())
        print_info(f"Dumped cleaned API docs to {clean_dir}")

        self.vectorstore = FAISS.from_documents(vsfiles, OpenAIEmbeddings())
        self.vectorstore.save_local(clean_dir + ".faiss")
        print_info(f"Cached vectorstore at {clean_dir}.faiss")

    def load_cleaned_api_docs(self, api_tree_merged_file, clean_dir, cmd_prefix):
        """
        If we have already cleaned the API docs by calling `load_api_docs` before,
        we can load them directly by calling this function to save time
        """
        with open(api_tree_merged_file, "r") as f:
            self.cmd_by_category = yaml.safe_load(f)

        clean_api_files = [
            os.path.join(dp, f)
            for dp, dn, fn in os.walk(os.path.expanduser(clean_dir))
            for f in fn
        ]
        for file in clean_api_files:
            with open(file, "r") as f:
                data = yaml.safe_load(f)

            for cmd in data["directCommands"]:
                cmd_info = {"name": cmd["name"], "summary": cmd["summary"]}
                if "requiredParameters" in cmd:
                    cmd_info["requiredParameters"] = {}
                    req_args = cmd["requiredParameters"]
                    for name, summary in req_args.items():
                        cmd_info["requiredParameters"][name] = {
                            "summary": summary["summary"]
                        }

                self.cmd_dict[cmd["name"][len(cmd_prefix) :]] = cmd_info

        self.vectorstore = FAISS.load_local(
            clean_dir + ".faiss",
            OpenAIEmbeddings(),
            allow_dangerous_deserialization=True,
        )
        print_info(f"Loaded {len(self.cmd_dict)} query APIs from {clean_dir}")

    def select_category_by_tftype(
        self, tf_type: str, tf_prefix: str, cloud_type: str, failed=[]
    ):
        """
        Given a Terraform type, select the API category that should contains cloud query commands for this type
        """
        assert (
            self.vectorstore
        ), "Please load the API docs by calling `load_api_docs` or `load_cleaned_api_docs` first"
        print_info(f"Selecting category for Terraform type: {tf_type}")
        tf_type = tf_type[len(tf_prefix) :]

        doc_retriever = self.vectorstore.as_retriever(
            search_kwargs={"k": Config["select_cli_category_retrieve_k"]}
        )
        retrieve_query = (
            f"Find an API to list all IDs of Terraform `{tf_type}` resource type"
        )
        docs = doc_retriever.invoke(retrieve_query)

        category_info = {}
        print_info("Retrieved documents:")
        for doc in docs:
            content = yaml.safe_load(doc.page_content)
            if content["category"] in failed:
                continue
            category_info[content["category"]] = content["summary"]
            print(doc.metadata["source"].split("/")[-1])

        select_query = self.__get_select_message(tf_type, category_info, cloud_type)

        selected_category = self.agent.invoke(select_query).strip('"')
        print_info(f"Selected category: {selected_category}")
        return selected_category

    def __get_select_message(
        self, tf_type: str, category_info: dict, cloud_type="Azure"
    ):
        return [
            SystemMessage(
                f"You are a helpful {cloud_type} Cloud customer support assistant. \
                Your customer is asking to query cloud resource IDs corresponding to Terraform resource types, \
                so they can use those ID for `terraform import`."
            ),
            HumanMessage(
                f"I want to list the IDs of all '{tf_type}' in my subscription,\
                it is possible that I need to query the parent resource before querying the this one.\
                which category should I look for the command in the {cloud_type} CLI documentation?\
                Please only return the category name as a string.\n"
                + json.dumps(category_info, indent=4)
            ),
        ]

    def get_cmd_dict(self):
        return self.cmd_dict

    def get_cmd_by_category(self, category):
        return self.cmd_by_category[category]
