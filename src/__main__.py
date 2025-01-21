import os
import argparse

from utils import print_error
from inferWorker import AzureInferWorker
from ruleExtractor import AzureRuleExtractor

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Lilac - Automated IaC lifting rule extraction (query) and utilization (lift)"
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "-q",
        "--query",
        action="store_true",
        help="Extract lifting rules from test programs",
    )
    mode.add_argument(
        "-l",
        "--lift",
        action="store_true",
        help="Lift the infrastructure based on extracted rules",
    )

    parser.add_argument(
        "-t",
        "--test-dir",
        nargs="+",
        help="Directory containing Terraform test programs for lifting rule extraction",
    )

    parser.add_argument(
        "-r",
        "--rule-dir",
        nargs="+",
        help="Directory containing lifting rules for cloud infrastructure lifting",
    )

    parser.add_argument(
        "-g",
        "--resource-group",
        help="Name of Azure resource group to be lifted",
    )

    parser.add_argument(
        "-s",
        "--save-path",
        help="Path to save the lifted Terraform file of the resource group",
    )

    args = parser.parse_args()

    if args.query:
        test_dirs = [os.path.join("test", d) for d in args.test_dir]
        if not test_dirs:
            print_error("[WARNNING] No test directory provided")
        ruleExtractor = AzureRuleExtractor()
        ruleExtractor.schedule_tests(test_dirs)

    elif args.lift:
        rule_dirs = [os.path.join("test", d) for d in args.rule_dir]
        if not rule_dirs:
            print_error("[WARNNING] No rule directory provided")
        rule_files = [
            os.path.join(rule_dir, f)
            for rule_dir in rule_dirs
            for f in os.listdir(rule_dir)
            if f.endswith(".json")
        ]
        if not args.resource_group:
            print_error("[WARNNING] No resource group provided")
        inferController = AzureInferWorker(args.resource_group)
        inferController.prepare_infer_rules(rule_files)
        inferController.lifting_inference()

        save_path = args.save_path
        if not save_path:
            print_error("[WARNNING] No save path provided, default to output/lifted.tf")
            save_path = os.path.join("output", "lifted.tf")
        inferController.save_lifted_instances(save_path)
