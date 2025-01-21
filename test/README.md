# Test case

Each sub-folder here stores one test case, which could include multiple Terraform resources. An example test program contains [a virtual machine with a data disk attached](https://github.com/jingjia-peng/Lilac-v0/blob/main/test/virtual_machine_data_disk_attachment/main.tf).

By running the query phase on this test, you could see the resulting folder structures like

```
virtual_machine_data_disk_attachment/
├── incremental_test/
│   ├── test_0/
│   │   └── main.tf # deployment for step-0 test
│   └── ...
├── main.tf # original test program
└── *-query-chain.json # record of cloud query steps
```
