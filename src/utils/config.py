import os

import yaml

# TODO: set the path to the config file, e.g. "api-config-example.yml"
api_config_path = os.path.join("config", "api-config.yml")

with open(api_config_path, "r") as f:
    api_config = yaml.safe_load(f)

with open(os.path.join("config", "global-config.yml"), "r") as f:
    global_config = yaml.safe_load(f)

Config = {
    "model": api_config["model"],
    "api_version": api_config["api_version"],
    "api_key": api_config["api_key"],
    "azure_endpoint": api_config["azure_endpoint"],
    "organization": api_config["organization"],
    "GPT_TOOL_LIMIT": global_config["GPT_TOOL_LIMIT"],
    "select_cli_category_retrieve_k": global_config["select_cli_category_retrieve_k"],
}
