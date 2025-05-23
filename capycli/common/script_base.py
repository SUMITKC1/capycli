# -------------------------------------------------------------------------------
# Copyright (c) 2019-2024 Siemens
# All Rights Reserved.
# Author: thomas.graf@siemens.com
#
# SPDX-License-Identifier: MIT
# -------------------------------------------------------------------------------

"""
Base class for python scripts.
"""

import json
import os
import sys
from capycli.common.sw360_patch import patch_sw360_for_batch_update
patch_sw360_for_batch_update()
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import jwt
import requests
from cyclonedx.model.bom import Bom
from sw360 import SW360, SW360Error

from capycli.common.print import print_red, print_text, print_yellow
from capycli.main.result_codes import ResultCode


class ScriptBase:
    """Base class for python scripts."""

    def __init__(self) -> None:
        self.client: Optional[SW360] = None
        self.project_id: str = ""
        self.project: Optional[dict[str, Any]] = None
        self.sw360_url: str = os.environ.get("SW360ServerUrl", "")

    def login(self, token: str = "", url: str = "", oauth2: bool = False) -> bool:
        """Login to SW360"""
        self.sw360_url = os.environ.get("SW360ServerUrl", "")
        sw360_api_token = os.environ.get("SW360ProductionToken", "")

        if token:
            sw360_api_token = token

        if url:
            self.sw360_url = url

        if not self.sw360_url:
            print_red("  No SW360 server URL specified!")
            sys.exit(ResultCode.RESULT_ERROR_ACCESSING_SW360)

        if self.sw360_url[-1] != "/":
            self.sw360_url += "/"

        if not sw360_api_token:
            print_red("  No SW360 API token specified!")
            sys.exit(ResultCode.RESULT_AUTH_ERROR)

        self.client = SW360(self.sw360_url, sw360_api_token, oauth2)

        try:
            result = self.client.login_api(sw360_api_token)
        except SW360Error as swex:
            if (swex.response is not None) and (swex.response.status_code == requests.codes["unauthorized"]):
                print_red("  You are not authorized!")
                sys.exit(ResultCode.RESULT_AUTH_ERROR)
            else:
                print_red("  Error authorizing user: " + repr(swex))
                sys.exit(ResultCode.RESULT_AUTH_ERROR)

        return result

    def analyze_token(self, token: str) -> None:
        """Analyzes the user provided token.
        If we can decode it, then it is an OAuth2 token."""

        print_text("  Analyzing token...")
        try:
            # alg = RS256
            decoded = jwt.decode(token, verify=False)  # type: ignore
            if "exp" in decoded:
                exp_seconds = int(decoded["exp"])
                exp = datetime.fromtimestamp(exp_seconds)
                print_text("  Token will expire on " + str(exp))

            # print(decoded)
            # {
            #   'aud': ['sw360-REST-API'],
            #   'user_name': 'thomas.graf@siemens.com',
            #   'scope': ['READ', 'WRITE'],
            #   'exp': 1581754268,
            #   'authorities': ['READ', 'WRITE'],
            #   'jti': 'bddc8951-bfae-475d-b2fd-04059b86598e',
            #   'client_id': 'xxx'
            # }
        except Exception as ex:
            print_yellow("  Unable to analyze token:" + repr(ex))

    def get_error_message(self, swex: SW360Error) -> str:
        """Display a useful error message for a SW360Error exception"""
        if swex.response is None:
            return repr(swex)
        elif swex.response.status_code == requests.codes["forbidden"]:
            return "You are not authorized!"
        else:
            content = swex.response.content.decode("UTF8")
            jcontent = json.loads(content)
            text = "Error=" + jcontent["error"] + "(" +\
                str(jcontent["status"]) + "): " + jcontent["message"]
            return text

    @staticmethod
    def get_release_attachments(release_details: Dict[str, Any],
                                att_types: Optional[Tuple[str]] = None) -> List[Dict[str, Any]]:
        """Returns the attachments with the given types from a release. Use empty att_types
        to get all attachments."""
        if "_embedded" not in release_details:
            return []

        if "sw360:attachments" not in release_details["_embedded"]:
            return []

        found = []
        attachments = release_details["_embedded"]["sw360:attachments"]
        if not att_types:
            return attachments

        for attachment in attachments:
            if attachment["attachmentType"] in att_types:
                found.append(attachment)

        return found

    def release_web_url(self, release_id: str) -> str:
        """Returns the HTML URL for a given release_id."""
        return (self.sw360_url + "group/guest/components/-/component/release/detailRelease/"
                + release_id)

    def find_project(self, name: str, version: str, show_results: bool = False) -> str:
        """Find the project with the matching name and version on SW360"""
        if not self.client:
            print_red("  No client!")
            sys.exit(ResultCode.RESULT_ERROR_ACCESSING_SW360)

        print_text("  Searching for project...")
        try:
            projects = self.client.get_projects_by_name(name)
        except SW360Error as swex:
            print_red("  Error searching for project: " + repr(swex))
            sys.exit(ResultCode.RESULT_ERROR_ACCESSING_SW360)

        if not projects:
            print_yellow("  No matching project found!")
            return ""

        for project in projects:
            href = project["_links"]["self"]["href"]
            if "version" not in project:
                if show_results:
                    print_text(
                        "    "
                        + project["name"]
                        + " => ID = "
                        + self.client.get_id_from_href(href)
                    )
            else:
                pid = self.client.get_id_from_href(href)
                if show_results:
                    print_text(
                        "    "
                        + project["name"]
                        + ", "
                        + project["version"]
                        + " => ID = "
                        + pid
                    )
                if project["version"].lower() == version.lower():
                    return pid

        return ""

    @staticmethod
    def get_comp_count_text(bom: Bom) -> str:
        count = len(bom.components)
        if count == 1:
            return "1 component"
        else:
            return f"{count} components"

    @staticmethod
    def list_to_string(list: List[str]) -> str:
        """Convert a list of values to a comma separated string"""
        result = ", ".join(str(x) for x in list)
        return result
