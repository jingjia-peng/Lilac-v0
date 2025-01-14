import os

import yaml

# TODO: set the path to the config file, e.g. "example.yaml"
config_path = os.path.join("config", "config.yaml")

with open(config_path, "r") as f:
    config = yaml.safe_load(f)

Config = {
    "model": config["model"],
    "api_version": config["api_version"],
    "api_key": config["api_key"],
    "azure_endpoint": config["azure_endpoint"],
    "organization": config["organization"],
}
