#!/usr/bin/env python3
"""Read-only credential smoke tests for the four China cloud catalogs."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable


PROVIDER_SECRETS = {
    "alibaba": (
        "ALIBABA_CLOUD_ACCESS_KEY_ID",
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
    ),
    "tencent": (
        "TENCENTCLOUD_SECRET_ID",
        "TENCENTCLOUD_SECRET_KEY",
    ),
    "volcengine": (
        "VOLCENGINE_ACCESS_KEY_ID",
        "VOLCENGINE_SECRET_ACCESS_KEY",
    ),
    "huawei": (
        "HUAWEI_ACCESS_KEY_ID",
        "HUAWEI_SECRET_ACCESS_KEY",
    ),
}


def credentials(provider: str) -> tuple[str, str]:
    names = PROVIDER_SECRETS[provider]
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"missing GitHub Secret(s): {', '.join(missing)}")
    return os.environ[names[0]], os.environ[names[1]]


def smoke_alibaba() -> int:
    from aliyunsdkcore.client import AcsClient
    from aliyunsdkecs.request.v20140526.DescribeInstanceTypesRequest import (
        DescribeInstanceTypesRequest,
    )

    access_key_id, access_key_secret = credentials("alibaba")
    client = AcsClient(
        access_key_id,
        access_key_secret,
        "cn-hangzhou",
        auto_retry=True,
        max_retry_time=2,
        connect_timeout=10,
        timeout=30,
        port=443,
    )
    request = DescribeInstanceTypesRequest()
    request.set_protocol_type("https")
    request.set_accept_format("json")
    request.set_MaxResults(10)
    payload = json.loads(client.do_action_with_exception(request))
    return len(payload.get("InstanceTypes", {}).get("InstanceType", []))


def smoke_tencent() -> int:
    from tencentcloud.common.credential import Credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.cvm.v20170312 import cvm_client, models

    secret_id, secret_key = credentials("tencent")
    http_profile = HttpProfile()
    http_profile.keepAlive = True
    http_profile.reqTimeout = 30
    client_profile = ClientProfile(httpProfile=http_profile, language="en-US")
    client = cvm_client.CvmClient(
        Credential(secret_id, secret_key), "ap-beijing", client_profile
    )
    response = client.DescribeInstanceTypeConfigs(
        models.DescribeInstanceTypeConfigsRequest()
    )
    return len(response.InstanceTypeConfigSet or [])


def smoke_volcengine() -> int:
    import volcenginesdkcore
    import volcenginesdkecs

    access_key_id, secret_access_key = credentials("volcengine")
    configuration = volcenginesdkcore.Configuration()
    configuration.ak = access_key_id
    configuration.sk = secret_access_key
    configuration.region = "cn-beijing"
    configuration.connect_timeout = 10
    configuration.read_timeout = 30
    client = volcenginesdkecs.ECSApi(volcenginesdkcore.ApiClient(configuration))
    response = client.describe_instance_types(
        volcenginesdkecs.DescribeInstanceTypesRequest(max_results=10)
    )
    return len(response.instance_types or [])


def smoke_huawei() -> int:
    from huaweicloudsdkcore.auth.credentials import BasicCredentials
    from huaweicloudsdkcore.http.http_config import HttpConfig
    from huaweicloudsdkecs.v2 import EcsClient, ListFlavorsRequest
    from huaweicloudsdkecs.v2.region.ecs_region import EcsRegion

    access_key_id, secret_access_key = credentials("huawei")
    http_config = HttpConfig.get_default_config()
    http_config.timeout = (10, 30)
    client = (
        EcsClient.new_builder()
        .with_credentials(BasicCredentials(access_key_id, secret_access_key))
        .with_http_config(http_config)
        .with_region(EcsRegion.value_of("cn-north-4"))
        .build()
    )
    response = client.list_flavors(ListFlavorsRequest(limit=10))
    return len(response.flavors or [])


def safe_error(error: Exception) -> str:
    message = str(error)
    for names in PROVIDER_SECRETS.values():
        for name in names:
            value = os.environ.get(name)
            if value:
                message = message.replace(value, "***")
    message = " ".join(message.split())
    return message[:500] or error.__class__.__name__


def main() -> int:
    tests: list[tuple[str, Callable[[], int]]] = [
        ("alibaba", smoke_alibaba),
        ("tencent", smoke_tencent),
        ("volcengine", smoke_volcengine),
        ("huawei", smoke_huawei),
    ]
    failures = 0
    for provider, test in tests:
        try:
            count = test()
            if count < 1:
                raise RuntimeError("API returned zero instance types")
            print(f"{provider}: OK ({count} instance types in smoke response)")
        except Exception as error:  # Keep testing the remaining providers.
            failures += 1
            print(
                f"::error title={provider} API smoke failed::"
                f"{error.__class__.__name__}: {safe_error(error)}"
            )

    if failures:
        print(f"China cloud API smoke failed for {failures}/{len(tests)} providers")
        return 1
    print("China cloud API smoke passed for all providers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
