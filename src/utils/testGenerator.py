import os
import shutil
import subprocess
from collections import namedtuple

import pydot
import networkx as nx
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser

from utils import Config, print_info

PartialOrder = namedtuple("PartialOrder", ["src", "dest"])


def print_partial_orders(partial_orders: list):
    print("Partial Orders:")
    for po in partial_orders:
        print_info(po.src, "->", po.dest)


def print_total_orders(total_orders: list):
    print("Generated incremental tests:")
    for i, order in enumerate(total_orders[::-1]):
        print_info(f"test_{i}: {order}")


def get_partial_orders(dir: str):
    """
    Assume there's a Terraform project inside dir
    Obtain the partial orders of the resources in this Terraform project

    Need to guarantee only resource blocks are in the Terraform project
    """
    if not os.path.exists(os.path.join(dir, ".terraform")):
        subprocess.run("terraform init", shell=True, cwd=dir)

    result = subprocess.run(
        "terraform graph", shell=True, cwd=dir, stdout=subprocess.PIPE
    )
    result = result.stdout.decode("utf-8")
    with open(os.path.join(dir, "graph.dot"), "w") as f:
        f.write(result)

    graph = pydot.graph_from_dot_file(os.path.join(dir, "graph.dot"))
    edges = graph[0].get_edges()
    partialOrders = []
    for edge in edges:
        src = edge.get_source().strip('"')
        dest = edge.get_destination().strip('"')
        # only consider resources nodes
        if len(src.split(".")) == 2 and len(dest.split(".")) == 2:
            partialOrders.append(PartialOrder(src, dest))
    return partialOrders


def toposort(partial_orders: list[PartialOrder]):
    G = nx.DiGraph()
    for po in partial_orders:
        G.add_edge(po.src, po.dest)
    return list(nx.topological_sort(G))


def clean_output_tffile(basefiles: list[str]):
    """
    Clean all `output` blocks in origianl Terraform files.
    This avoids dependency issues in incremental test, where some `output` depends on undeclared resource.
    """
    rmfiles = []
    for file in basefiles:
        cmd = ["hcledit", "block", "-f", file, "-u", "rm", "output.*"]
        subprocess.run(cmd)
        result = subprocess.run(
            f"hcledit block -f {file} list", shell=True, stdout=subprocess.PIPE
        )
        if result.stdout.decode("utf-8") == "":
            os.remove(file)
            rmfiles.append(file)
    for file in rmfiles:
        basefiles.remove(file)


def generate_incremental_tests(basedir: str, verbose=False):
    """
    Generate incremental test cases based on the basefile.
    Return a list of test info (testdir, added_resource)

    Reference: https://github.com/minamijoyo/hcledit
    """
    testdir = os.path.join(basedir, "incremental_test")
    # clean the old testdir
    shutil.rmtree(testdir, ignore_errors=True)
    os.makedirs(testdir, exist_ok=True)

    partial_orders = get_partial_orders(basedir)
    total_orders = toposort(partial_orders)
    if verbose:
        print_total_orders(total_orders)

    basefiles = [
        os.path.join(dp, f)
        for dp, dn, fn in os.walk(os.path.expanduser(basedir))
        for f in fn
        if f.endswith(".tf")
        if "incremental" not in dp
    ]
    clean_output_tffile(basefiles)

    for i in range(len(total_orders)):
        test_path = os.path.join(testdir, f"test_{i}")
        os.makedirs(test_path, exist_ok=True)

        for basefile in basefiles:
            testfile = os.path.join(test_path, os.path.basename(basefile))
            shutil.copy(basefile, testfile)

            for j in range(len(total_orders) - 1 - i):
                cmd = [
                    "hcledit",
                    "block",
                    "-f",
                    testfile,
                    "-u",
                    "rm",
                    "resource." + total_orders[j],
                ]
                subprocess.run(cmd)

    return [
        (os.path.join(testdir, f"test_{i}"), total_orders[len(total_orders) - 1 - i])
        for i in range(len(total_orders))
    ]


def generate_unit_test(
    tf_type: str,
    cloud: str,
    res_cnst_msg: str,
    ref_file_path: str | None,
    result_dir: str,
    timeout=5,
) -> bool:
    """
    Generate unit tests for the given tf_type.
    If a reference file is provided, generate unit tests based on the reference file.
    Return True if the generated Terraform can be correctly deployed and used for later test.
    """
    agent = (
        AzureChatOpenAI(
            model=Config["model"],
            api_key=Config["api_key"],
            azure_endpoint=Config["azure_endpoint"],
            api_version=Config["api_version"],
            organization=Config["organization"],
        )
        | StrOutputParser()
    )

    messages = [
        SystemMessage(
            f"You are a useful assistance of {cloud} Terraform. \
        You are asked to generate a **minimum** Terraform program that contains {tf_type} {res_cnst_msg}\
        and can be correctly deployed. Please only return the code without any comment."
        ),
    ]
    if ref_file_path:
        with open(ref_file_path, "r") as f:
            ref_content = f.read()
        messages.append(
            HumanMessage(
                "Here is a reference program which might not be correct. \
            Common errors include missing provider blocks or incorrect resource attributes.\n "
                + ref_content
            )
        )

    result_file = os.path.join(result_dir, f"{tf_type}.tf")
    success = False

    for _ in range(timeout):
        response = agent.invoke(messages)

        lines = response.split("\n")
        start = False
        with open(result_file, "w") as f:
            for line in lines:
                if line.startswith("```") and not start:
                    start = True
                elif line.startswith("```") and start:
                    break
                elif start:
                    f.write(line + "\n")

        subprocess.run("terraform init", shell=True, cwd=result_dir)
        result = subprocess.run(
            "terraform plan",
            shell=True,
            cwd=result_dir,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode == 0:
            success = True
            break

        print(result.stderr)
        messages.append(
            HumanMessage(
                "Your generated Terraform fails to plan with the following error:\n"
                + result.stderr
            )
        )

    return success
