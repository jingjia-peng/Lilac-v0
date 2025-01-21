import os
import logging
import subprocess
from collections import namedtuple, defaultdict

from tabulate import tabulate

from utils import print_info

LiftedInstance = namedtuple("LiftedInstance", ["tftype", "id"])
ImportInstance = namedtuple("ImportInstance", ["tftype", "name", "id"])


class InferWorker:
    def __init__(self, infer_rule):
        self.infer_rule = infer_rule
        self.lifted_instances = []  # list of LiftedInstance
        self.import_instances = []  # list of ImportInstance

        # key: InferAPIArg, value: arg value
        self.apiarg_map = defaultdict(set)
        self.tfid_map = defaultdict(set)  # key: IDSchema, value: ID value

        logging.basicConfig(
            level=logging.WARNING,
            handlers=[
                logging.FileHandler("infer.log", "w", "utf-8"),
                logging.StreamHandler(),
            ],
        )
        self.logger = logging.getLogger(__name__)

        # suppress logging
        self.logger.disabled = True

    def prepare_infer_rules(self):
        raise NotImplementedError

    def lifting_inference(self):
        self._print_init_lifting()

        # BFS search for all resources by APIs
        api_queue = []

        # search from top-level resources in the resource group
        cloud_types = self._populate_top_api_queue(api_queue)
        print_info(f"Top-level resources types: {cloud_types}")
        self.logger.info(f"Top-level resources types: {cloud_types}")

        while api_queue:
            api = api_queue.pop(0)
            arg_names = self.infer_rule.get_required_args(api)  # set of arg_name

            # check if all arguments are ready
            arg_map = {}
            args_ready = self._resolve_args(api_queue, api, arg_names, arg_map)
            if not args_ready:
                api_queue.append(api)
                continue

            # run the API call and analyze the response
            full_api = self._get_full_api_call(api, arg_map)
            print_info(f"Running command: {full_api}")
            self.logger.info(f"Running command: {full_api}")
            result = subprocess.run(
                full_api, stdout=subprocess.PIPE, shell=True, text=True
            )
            if result.returncode != 0:
                continue

            # check if any info can be infered from the response
            response = self._get_resource_group_response(result.stdout)
            response_info = self.infer_rule.get_response_info(api)  # ResponseInfo
            self._analyze_response(response, response_info)

            # add relevant API calls to the queue
            for relevant_api in self.infer_rule.get_relevant_apis(api):
                if relevant_api not in api_queue:
                    api_queue.append(relevant_api)

        # after BFS, process the tfid_map to get the lifted instances
        tftypes = set()
        for schema in self.tfid_map:
            tftypes.add(schema.tftype)
        # check each inferable TF type
        for tftype in tftypes:
            self._infer_tfinstance(tftype)

        self.__post_process_instances()

    def _print_init_lifting(self):
        raise NotImplementedError

    def _resolve_args(self) -> bool:
        """
        Check if all required arguments are ready in the arg_map.
        """
        raise NotImplementedError

    def _populate_top_api_queue(self):
        """
        Search for top-level resources in the resource group and populate the API queue.
        Return the set of cloud types found in the resource group.
        """
        raise NotImplementedError

    def _analyze_response(self):
        raise NotImplementedError

    def _infer_tfinstance(self):
        raise NotImplementedError

    def save_lifted_instances(self, path: str, imported=False):
        """
        Save all the lifted instances to a Terraform file.
        If imported is True, run `terraform import` to pop up resource attributes.
        """
        self.print_instances()
        if os.path.exists(path):
            os.remove(path)
        if not imported:
            self._save_instance_topo(path)
        else:
            self._save_instance_imported(path)

    def print_instances(self):
        table = tabulate(
            self.import_instances, headers=["TF Type", "Name", "ID"], tablefmt="pretty"
        )
        print_info(table)
        self.logger.info(table)

    def __post_process_instances(self):
        tftypes = defaultdict(set)
        for instance in self.lifted_instances:
            tftypes[instance.tftype].add(instance.id)
        for tftype, ids in tftypes.items():
            for i, id in enumerate(ids):
                self.import_instances.append(ImportInstance(tftype, f"example-{i}", id))

    def _save_instance_topo(self):
        raise NotImplementedError

    def _save_instance_imported(self):
        raise NotImplementedError

    def _get_full_api_call(self):
        raise NotImplementedError

    def _get_resource_group_response(self):
        """
        Get all resources in the self resource group
        """
        raise NotImplementedError

    def _get_child_key(self, i: int, tfid_components: set):
        for component in tfid_components:
            if component.startswith(f"child_{i}"):
                return component
        return None
