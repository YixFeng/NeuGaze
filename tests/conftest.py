def pytest_addoption(parser):
    parser.addoption(
        "--run-orbbec",
        action="store_true",
        default=False,
        help="run tests that require connected Orbbec hardware",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "orbbec_hardware: requires connected Orbbec hardware"
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-orbbec"):
        return

    selected = []
    deselected = []
    for item in items:
        if "orbbec_hardware" in item.keywords:
            deselected.append(item)
        else:
            selected.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected
