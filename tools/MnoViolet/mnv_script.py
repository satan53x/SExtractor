#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M no Violet script VM tools.

The tool works on unpacked M no Violet script streams.  Archive unpacking and
packing live in mnv_tool.py; this file is intentionally self-contained and does
not require Hex-Rays C output at runtime.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
ENCODING = "cp932"
TEXT_OPCODE = 63
TEXT_NAME_PARAM = 0
TEXT_MESSAGE_PARAM = 1
DYNAMIC_OPS = {22, 23, 31}
INTERNAL_JUMP_OPS = {20, 21, 22, 24}

# Frozen from SACRIFICE.EXE sub_484670 and its handlers.  Each row is:
# (opcode, handler_name, handler_address, operand_template, dynamic, jump_helper)
EMBEDDED_OPCODE_ROWS = [(0, 'sub_498750', '00498750', ('INT', 'INT'), False, False), (1, 'sub_499550', '00499550', ('STR', 'STR'), False, False), (2, 'sub_4988C0', '004988C0', ('INT', 'INT'), False, False), (3, 'sub_498A30', '00498A30', ('INT', 'INT'), False, False), (4, 'sub_498BA0', '00498BA0', ('INT', 'INT'), False, False), (5, 'sub_498D10', '00498D10', ('INT', 'INT'), False, False), (6, 'sub_498EA0', '00498EA0', ('INT', 'INT'), False, False), (7, 'sub_499030', '00499030', ('INT', 'INT', 'INT'), False, False), (8, 'sub_4991E0', '004991E0', ('INT', 'INT', 'INT'), False, False), (9, 'sub_499380', '00499380', ('INT', 'INT', 'INT', 'INT'), False, False), (10, 'sub_4996F0', '004996F0', ('INT', 'STR'), False, False), (11, 'sub_499860', '00499860', ('STR', 'STR'), False, False), (12, 'sub_4999E0', '004999E0', ('STR', 'STR', 'INT'), False, False), (13, 'sub_499BC0', '00499BC0', ('STR', 'STR', 'INT'), False, False), (14, 'sub_499DF0', '00499DF0', ('STR', 'INT'), False, False), (15, 'sub_499F90', '00499F90', ('STR', 'INT'), False, False), (16, 'sub_49A150', '0049A150', ('INT', 'STR'), False, False), (17, 'sub_49A2D0', '0049A2D0', ('INT', 'INT'), False, False), (18, 'sub_49A440', '0049A440', ('INT', 'INT'), False, False), (20, 'sub_494260', '00494260', ('LBL',), False, True), (21, 'sub_4943D0', '004943D0', ('LBL',), False, True), (22, 'sub_494540', '00494540', ('INT', 'INT', 'LBL'), True, True), (23, 'sub_494770', '00494770', ('INT', 'INT', 'LBL'), True, True), (24, 'sub_4949A0', '004949A0', ('INT', 'INT', 'INT', 'LBL'), False, True), (25, 'sub_494BE0', '00494BE0', ('INT', 'INT', 'INT', 'LBL'), False, True), (26, 'sub_494E20', '00494E20', (), False, False), (27, 'sub_494F80', '00494F80', ('STR',), False, False), (28, 'sub_495130', '00495130', ('STR',), False, False), (29, 'sub_4952F0', '004952F0', (), False, False), (30, 'sub_495430', '00495430', ('INT', 'STR'), False, False), (31, 'sub_4955C0', '004955C0', ('INT', 'INT', 'INT', 'STR', 'INT'), True, False), (32, 'sub_4958B0', '004958B0', (), False, False), (33, 'sub_495A00', '00495A00', ('STR',), False, False), (40, 'sub_49A5C0', '0049A5C0', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (41, 'sub_49AC90', '0049AC90', ('INT', 'INT', 'INT', 'INT'), False, False), (42, 'sub_49AF40', '0049AF40', ('INT',), False, False), (43, 'sub_49B0C0', '0049B0C0', ('INT',), False, False), (44, 'sub_49B1F0', '0049B1F0', ('INT',), False, False), (45, 'sub_49B320', '0049B320', (), False, False), (46, 'sub_49B430', '0049B430', ('INT',), False, False), (47, 'sub_49B600', '0049B600', ('INT',), False, False), (48, 'sub_49B740', '0049B740', ('INT',), False, False), (49, 'sub_49B910', '0049B910', (), False, False), (50, 'sub_49BA10', '0049BA10', ('INT',), False, False), (51, 'sub_4873B0', '004873B0', ('INT', 'INT'), False, False), (52, 'sub_487540', '00487540', ('INT', 'INT'), False, False), (53, 'sub_487710', '00487710', ('INT', 'STR'), False, False), (54, 'sub_487940', '00487940', ('INT',), False, False), (60, 'sub_496010', '00496010', ('INT', 'STR'), False, False), (61, 'sub_4964F0', '004964F0', ('STR',), False, False), (62, 'sub_496650', '00496650', (), False, False), (63, 'sub_4966B0', '004966B0', ('INT', 'STR', 'STR'), False, False), (64, 'sub_4969E0', '004969E0', ('INT', 'STR', 'INT', 'INT', 'INT', 'INT', 'STR'), False, False), (65, 'sub_496EB0', '00496EB0', ('STR', 'STR'), False, False), (66, 'sub_497020', '00497020', ('INT',), False, False), (70, 'sub_48CAA0', '0048CAA0', ('INT', 'INT'), False, False), (80, 'sub_48CC00', '0048CC00', ('INT', 'INT', 'INT', 'INT'), False, False), (81, 'sub_48CDC0', '0048CDC0', ('INT',), False, False), (82, 'sub_48CF00', '0048CF00', ('INT', 'STR', 'INT', 'INT'), False, False), (83, 'sub_48D100', '0048D100', ('INT', 'INT', 'INT', 'INT'), False, False), (90, 'sub_48D350', '0048D350', ('INT', 'STR'), False, False), (91, 'sub_48D4F0', '0048D4F0', ('INT',), False, False), (100, 'sub_4902D0', '004902D0', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (101, 'sub_490560', '00490560', ('INT',), False, False), (102, 'sub_490690', '00490690', (), False, False), (103, 'sub_490790', '00490790', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (104, 'sub_490A10', '00490A10', ('INT', 'INT', 'INT', 'INT'), False, False), (105, 'sub_490BD0', '00490BD0', ('INT',), False, False), (106, 'sub_490D00', '00490D00', (), False, False), (107, 'sub_490E00', '00490E00', ('INT', 'INT'), False, False), (108, 'sub_490F50', '00490F50', ('INT',), False, False), (109, 'sub_491070', '00491070', ('INT', 'INT'), False, False), (110, 'sub_4911F0', '004911F0', ('INT', 'INT'), False, False), (111, 'sub_491370', '00491370', ('INT', 'INT'), False, False), (112, 'sub_4914F0', '004914F0', ('INT', 'INT'), False, False), (113, 'sub_491670', '00491670', ('INT', 'INT'), False, False), (114, 'sub_491800', '00491800', ('INT', 'INT'), False, False), (115, 'sub_491990', '00491990', ('INT', 'INT'), False, False), (120, 'sub_491AE0', '00491AE0', ('INT', 'STR', 'INT', 'INT', 'INT'), False, False), (121, 'sub_491CF0', '00491CF0', (), False, False), (122, 'sub_491DF0', '00491DF0', ('INT',), False, False), (123, 'sub_491F20', '00491F20', (), False, False), (124, 'sub_492020', '00492020', ('INT', 'INT'), False, False), (125, 'sub_492170', '00492170', ('INT',), False, False), (126, 'sub_492290', '00492290', ('INT', 'INT'), False, False), (127, 'sub_492420', '00492420', (), False, False), (128, 'sub_492520', '00492520', ('INT', 'INT'), False, False), (129, 'sub_492670', '00492670', ('INT', 'STR', 'INT'), False, False), (130, 'sub_492810', '00492810', ('INT', 'INT', 'INT'), False, False), (131, 'sub_4929C0', '004929C0', ('INT', 'INT'), False, False), (132, 'sub_492B40', '00492B40', ('INT', 'INT'), False, False), (133, 'sub_492CC0', '00492CC0', ('INT', 'INT'), False, False), (134, 'sub_492E40', '00492E40', ('INT', 'INT'), False, False), (140, 'sub_492F90', '00492F90', ('INT', 'STR'), False, False), (141, 'sub_493130', '00493130', ('INT',), False, False), (142, 'sub_493270', '00493270', (), False, False), (143, 'sub_493370', '00493370', ('INT', 'INT', 'INT'), False, False), (144, 'sub_493570', '00493570', ('INT', 'INT'), False, False), (145, 'sub_493720', '00493720', ('INT', 'INT', 'INT'), False, False), (146, 'sub_493900', '00493900', ('INT',), False, False), (147, 'sub_493A50', '00493A50', ('INT',), False, False), (148, 'sub_493BA0', '00493BA0', (), False, False), (149, 'sub_493D00', '00493D00', ('INT',), False, False), (150, 'sub_493E50', '00493E50', (), False, False), (151, 'sub_493FB0', '00493FB0', ('INT',), False, False), (152, 'sub_494100', '00494100', (), False, False), (160, 'sub_48D630', '0048D630', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (161, 'sub_48D930', '0048D930', ('INT', 'INT', 'INT', 'INT', 'INT'), False, False), (162, 'sub_48DB70', '0048DB70', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (163, 'sub_48DFE0', '0048DFE0', ('INT', 'INT', 'INT', 'INT', 'INT'), False, False), (164, 'sub_48E220', '0048E220', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (165, 'sub_48E4C0', '0048E4C0', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (166, 'sub_48E790', '0048E790', ('INT', 'INT'), False, False), (167, 'sub_48E940', '0048E940', ('INT', 'INT'), False, False), (168, 'sub_48EAF0', '0048EAF0', ('INT', 'INT', 'INT', 'INT', 'INT'), False, False), (169, 'sub_48ED30', '0048ED30', ('INT', 'INT', 'INT', 'INT'), False, False), (170, 'sub_48EF40', '0048EF40', ('INT',), False, False), (180, 'sub_48B900', '0048B900', ('INT', 'INT', 'INT'), False, False), (181, 'sub_48BA90', '0048BA90', ('INT',), False, False), (182, 'sub_48BBD0', '0048BBD0', (), False, False), (183, 'sub_48BCD0', '0048BCD0', ('INT', 'INT', 'INT', 'INT', 'INT'), False, False), (184, 'sub_48BEB0', '0048BEB0', ('STR', 'INT', 'INT'), False, False), (185, 'sub_48C070', '0048C070', ('INT', 'STR', 'INT', 'INT'), False, False), (186, 'sub_48C270', '0048C270', ('INT',), False, False), (187, 'sub_48C3D0', '0048C3D0', ('INT',), False, False), (188, 'sub_48C530', '0048C530', ('INT',), False, False), (189, 'sub_48C690', '0048C690', ('INT',), False, False), (190, 'sub_48C7E0', '0048C7E0', ('INT',), False, False), (191, 'sub_48C940', '0048C940', ('INT',), False, False), (200, 'sub_48F080', '0048F080', (), False, False), (201, 'sub_48F180', '0048F180', ('INT', 'INT', 'INT', 'INT', 'INT'), False, False), (202, 'sub_48F380', '0048F380', ('INT', 'INT', 'INT'), False, False), (203, 'sub_48F520', '0048F520', ('INT',), False, False), (204, 'sub_48F680', '0048F680', ('INT',), False, False), (205, 'sub_48F7E0', '0048F7E0', ('INT',), False, False), (206, 'sub_48F940', '0048F940', ('INT',), False, False), (207, 'sub_48FA90', '0048FA90', ('INT',), False, False), (208, 'sub_48FBF0', '0048FBF0', ('INT',), False, False), (209, 'sub_48FD50', '0048FD50', ('INT',), False, False), (210, 'sub_48FEB0', '0048FEB0', ('INT',), False, False), (211, 'sub_490010', '00490010', ('INT',), False, False), (212, 'sub_490170', '00490170', ('INT',), False, False), (220, 'sub_497140', '00497140', ('STR', 'INT'), False, False), (221, 'sub_4972E0', '004972E0', (), False, False), (222, 'sub_497400', '00497400', ('INT', 'INT'), False, False), (223, 'sub_497580', '00497580', ('STR', 'INT'), False, False), (224, 'sub_4221E0', '004221E0', (), False, False), (225, 'sub_4976D0', '004976D0', ('INT', 'INT'), False, False), (226, 'sub_497810', '00497810', ('STR', 'INT', 'INT'), False, False), (227, 'sub_497A40', '00497A40', (), False, False), (228, 'sub_497B60', '00497B60', ('INT', 'STR'), False, False), (229, 'sub_497D00', '00497D00', ('INT',), False, False), (230, 'sub_497E20', '00497E20', (), False, False), (231, 'sub_497F20', '00497F20', ('INT', 'INT', 'STR'), False, False), (232, 'sub_4980F0', '004980F0', ('INT',), False, False), (233, 'sub_498210', '00498210', (), False, False), (234, 'sub_498310', '00498310', ('INT', 'STR'), False, False), (235, 'sub_4984B0', '004984B0', (), False, False), (236, 'sub_4985E0', '004985E0', ('STR',), False, False), (240, 'sub_489570', '00489570', ('INT',), False, False), (241, 'sub_4896C0', '004896C0', (), False, False), (242, 'sub_489760', '00489760', ('INT',), False, False), (243, 'sub_4898A0', '004898A0', (), False, False), (244, 'sub_4898E0', '004898E0', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (245, 'sub_489B90', '00489B90', ('INT',), False, False), (246, 'sub_489D10', '00489D10', ('INT',), False, False), (247, 'sub_489E80', '00489E80', ('INT', 'INT'), False, False), (250, 'sub_48A870', '0048A870', ('INT', 'STR'), False, False), (251, 'sub_48AA10', '0048AA10', ('INT', 'STR', 'INT'), False, False), (252, 'sub_48AC40', '0048AC40', ('INT', 'STR'), False, False), (253, 'sub_48AE50', '0048AE50', ('INT', 'INT', 'INT', 'INT', 'INT'), False, False), (254, 'sub_48B0B0', '0048B0B0', ('INT', 'INT', 'INT', 'INT'), False, False), (255, 'sub_48B2C0', '0048B2C0', ('INT', 'INT', 'INT', 'INT', 'INT', 'STR', 'STR'), False, False), (256, 'sub_48B610', '0048B610', ('INT', 'INT', 'INT', 'INT', 'STR', 'STR'), False, False), (260, 'sub_49C740', '0049C740', ('INT', 'INT', 'INT'), False, False), (261, 'sub_49C9D0', '0049C9D0', ('INT',), False, False), (262, 'sub_49CB10', '0049CB10', (), False, False), (263, 'sub_49CC10', '0049CC10', ('INT', 'INT', 'INT'), False, False), (264, 'sub_49CE00', '0049CE00', ('INT', 'INT'), False, False), (265, 'sub_49CF50', '0049CF50', ('INT', 'INT'), False, False), (266, 'sub_49D0E0', '0049D0E0', ('INT',), False, False), (267, 'sub_49D200', '0049D200', ('INT', 'INT'), False, False), (268, 'sub_49D390', '0049D390', ('INT', 'INT', 'INT'), False, False), (269, 'sub_49D660', '0049D660', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (270, 'sub_49D8C0', '0049D8C0', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (271, 'sub_49DD20', '0049DD20', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (272, 'sub_49E9F0', '0049E9F0', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'STR', 'INT'), False, False), (273, 'sub_49EE90', '0049EE90', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'STR', 'INT'), False, False), (274, 'sub_49F370', '0049F370', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'STR', 'INT'), False, False), (275, 'sub_49F9A0', '0049F9A0', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'STR', 'INT'), False, False), (276, 'sub_4A0050', '004A0050', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (277, 'sub_4A0400', '004A0400', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'STR'), False, False), (278, 'sub_4A0A00', '004A0A00', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'STR', 'INT', 'INT'), False, False), (279, 'sub_4A0ED0', '004A0ED0', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (280, 'sub_4A1590', '004A1590', ('INT', 'INT', 'INT', 'STR'), False, False), (281, 'sub_4A1990', '004A1990', ('INT', 'INT', 'INT', 'INT', 'INT', 'STR'), False, False), (282, 'sub_4A1E30', '004A1E30', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (283, 'sub_4A24E0', '004A24E0', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (284, 'sub_4A2950', '004A2950', ('INT', 'INT', 'INT', 'INT', 'STR', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (285, 'sub_4A2DF0', '004A2DF0', ('INT', 'INT'), False, False), (286, 'sub_4A2FF0', '004A2FF0', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (287, 'sub_4A3770', '004A3770', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (288, 'sub_4A3FF0', '004A3FF0', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (289, 'sub_4A45A0', '004A45A0', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (290, 'sub_4A4A90', '004A4A90', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (291, 'sub_4A5030', '004A5030', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (292, 'sub_4A53E0', '004A53E0', ('INT', 'INT', 'INT'), False, False), (293, 'sub_4A55F0', '004A55F0', ('INT', 'INT', 'INT', 'INT'), False, False), (294, 'sub_4A5820', '004A5820', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (295, 'sub_4A5B50', '004A5B50', ('INT', 'INT', 'INT', 'INT'), False, False), (296, 'sub_4A5DF0', '004A5DF0', ('INT', 'INT', 'STR'), False, False), (297, 'sub_4A6070', '004A6070', ('INT', 'INT', 'INT', 'INT'), False, False), (298, 'sub_4A62C0', '004A62C0', ('INT', 'INT', 'INT', 'INT'), False, False), (299, 'sub_4A6540', '004A6540', ('INT', 'INT', 'INT'), False, False), (300, 'sub_4A6760', '004A6760', ('INT', 'INT', 'INT', 'INT', 'INT'), False, False), (301, 'sub_4A6A10', '004A6A10', ('INT', 'INT', 'INT'), False, False), (302, 'sub_4A6C20', '004A6C20', ('INT', 'INT', 'INT'), False, False), (303, 'sub_4A6E30', '004A6E30', ('INT', 'INT', 'STR'), False, False), (304, 'sub_4A70A0', '004A70A0', ('INT', 'INT', 'INT'), False, False), (305, 'sub_4A72B0', '004A72B0', ('INT', 'INT', 'INT'), False, False), (306, 'sub_4A74D0', '004A74D0', ('INT', 'INT', 'STR'), False, False), (307, 'sub_4A7750', '004A7750', ('INT', 'INT'), False, False), (308, 'sub_4A7B10', '004A7B10', ('INT', 'INT', 'INT'), False, False), (309, 'sub_4A7FE0', '004A7FE0', ('INT', 'INT'), False, False), (310, 'sub_4A83E0', '004A83E0', ('INT', 'INT', 'INT', 'INT'), False, False), (311, 'sub_4A8920', '004A8920', ('INT', 'INT', 'INT', 'INT', 'INT', 'STR', 'INT', 'INT', 'INT'), False, False), (312, 'sub_4A8CE0', '004A8CE0', ('INT', 'INT', 'INT'), False, False), (313, 'sub_4A8EF0', '004A8EF0', ('INT', 'INT', 'INT'), False, False), (314, 'sub_4A9100', '004A9100', ('INT', 'INT', 'INT'), False, False), (315, 'sub_4A9310', '004A9310', ('INT', 'INT', 'INT', 'INT', 'INT', 'STR', 'STR', 'INT', 'INT', 'INT'), False, False), (316, 'sub_4A9820', '004A9820', ('INT', 'INT', 'INT'), False, False), (317, 'sub_4A9A40', '004A9A40', ('INT', 'INT', 'INT'), False, False), (318, 'sub_4A9C70', '004A9C70', ('INT', 'INT', 'STR'), False, False), (319, 'sub_4A9F20', '004A9F20', ('INT', 'INT', 'INT', 'STR'), False, False), (320, 'sub_4AA1E0', '004AA1E0', ('INT', 'INT', 'INT'), False, False), (321, 'sub_4AA400', '004AA400', ('INT', 'INT', 'INT'), False, False), (322, 'sub_4AA620', '004AA620', ('INT', 'INT', 'INT'), False, False), (350, 'sub_49BBB0', '0049BBB0', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (352, 'sub_49BE60', '0049BE60', ('INT',), False, False), (353, 'sub_49BF80', '0049BF80', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'STR', 'INT'), False, False), (354, 'sub_49C420', '0049C420', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (360, 'sub_495B90', '00495B90', ('INT',), False, False), (361, 'sub_495CC0', '00495CC0', ('INT', 'INT', 'INT'), False, False), (362, 'sub_495EA0', '00495EA0', ('INT', 'INT', 'INT'), False, False), (370, 'sub_487B00', '00487B00', ('STR', 'INT'), False, False), (371, 'sub_487C90', '00487C90', ('STR', 'INT'), False, False), (372, 'sub_487E00', '00487E00', ('STR', 'STR'), False, False), (373, 'sub_487F90', '00487F90', ('STR', 'STR'), False, False), (374, 'sub_488100', '00488100', ('STR', 'INT'), False, False), (375, 'sub_488290', '00488290', ('STR', 'INT'), False, False), (376, 'sub_488400', '00488400', ('STR', 'STR'), False, False), (377, 'sub_488590', '00488590', ('STR', 'STR'), False, False), (378, 'sub_488700', '00488700', ('INT', 'INT', 'INT', 'INT'), False, False), (379, 'sub_488920', '00488920', (), False, False), (380, 'sub_488AB0', '00488AB0', (), False, False), (381, 'sub_488C20', '00488C20', (), False, False), (382, 'sub_488E30', '00488E30', ('INT',), False, False), (383, 'sub_489090', '00489090', ('INT',), False, False), (384, 'sub_489250', '00489250', (), False, False), (385, 'sub_489350', '00489350', (), False, False), (386, 'sub_489450', '00489450', (), False, False), (390, 'sub_48A000', '0048A000', ('INT',), False, False), (391, 'sub_48A120', '0048A120', ('INT',), False, False), (392, 'sub_48A290', '0048A290', ('INT', 'INT'), False, False), (393, 'sub_48A430', '0048A430', ('INT', 'INT'), False, False), (400, 'sub_48A610', '0048A610', (), False, False), (401, 'sub_48A660', '0048A660', ('STR', 'STR'), False, False), (402, 'sub_48A7D0', '0048A7D0', (), False, False), (600, 'sub_4CFDC0', '004CFDC0', (), False, False), (601, 'sub_4CFEC0', '004CFEC0', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (602, 'sub_4D02A0', '004D02A0', ('INT', 'INT', 'INT', 'INT'), False, False), (603, 'sub_4D06D0', '004D06D0', ('INT', 'INT', 'INT', 'INT'), False, False), (604, 'sub_4D0890', '004D0890', ('INT',), False, False), (605, 'sub_4D09D0', '004D09D0', ('INT',), False, False), (610, 'sub_4D0E40', '004D0E40', ('INT', 'INT', 'INT', 'INT', 'INT'), False, False), (611, 'sub_4D18F0', '004D18F0', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (612, 'sub_4D2190', '004D2190', ('INT', 'INT', 'INT', 'INT'), False, False), (613, 'sub_4D2860', '004D2860', ('INT',), False, False), (620, 'sub_4D0AF0', '004D0AF0', (), False, False), (621, 'sub_4D0BF0', '004D0BF0', (), False, False), (622, 'sub_4D0D40', '004D0D40', (), False, False), (623, 'sub_4D2F40', '004D2F40', ('INT',), False, False), (624, 'sub_4D3070', '004D3070', ('INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT', 'INT'), False, False), (630, 'sub_4D3520', '004D3520', ('INT',), False, False), (632, 'sub_4D3830', '004D3830', ('INT', 'INT'), False, False), (633, 'sub_4D3E70', '004D3E70', ('INT',), False, False), (634, 'sub_4D3FB0', '004D3FB0', ('INT', 'INT'), False, False), (635, 'sub_4D4100', '004D4100', ('INT',), False, False), (636, 'sub_4D4270', '004D4270', ('INT', 'INT', 'INT', 'INT'), False, False), (637, 'sub_4D4530', '004D4530', ('INT',), False, False), (638, 'sub_4D4650', '004D4650', ('INT', 'INT', 'INT', 'INT'), False, False), (639, 'sub_4D4950', '004D4950', ('INT',), False, False), (640, 'sub_4D4AF0', '004D4AF0', ('INT', 'INT', 'INT'), False, False), (641, 'sub_4D4E40', '004D4E40', ('INT', 'INT'), False, False), (650, 'sub_4D5020', '004D5020', ('INT', 'INT'), False, False), (651, 'sub_4D5210', '004D5210', ('INT', 'INT'), False, False), (652, 'sub_4D5550', '004D5550', ('INT', 'INT', 'INT'), False, False), (653, 'sub_4D5930', '004D5930', ('INT', 'INT', 'INT'), False, False), (654, 'sub_4D5EC0', '004D5EC0', ('INT', 'INT', 'INT'), False, False), (655, 'sub_4D6020', '004D6020', ('INT', 'INT', 'INT'), False, False), (656, 'sub_4D62D0', '004D62D0', ('INT', 'INT', 'INT'), False, False), (657, 'sub_4D6560', '004D6560', ('INT', 'INT', 'INT'), False, False), (658, 'sub_4D6840', '004D6840', ('INT', 'INT', 'INT', 'INT'), False, False), (659, 'sub_4D6A10', '004D6A10', ('INT', 'INT', 'INT', 'INT'), False, False), (660, 'sub_4D6DD0', '004D6DD0', ('INT', 'INT'), False, False), (661, 'sub_4D6F60', '004D6F60', ('INT',), False, False), (662, 'sub_4D7280', '004D7280', ('INT', 'INT', 'INT', 'INT'), False, False), (670, 'sub_4D7470', '004D7470', ('INT',), False, False), (671, 'sub_4D75A0', '004D75A0', ('INT',), False, False), (672, 'sub_4D76C0', '004D76C0', ('INT',), False, False), (673, 'sub_4D77F0', '004D77F0', ('INT', 'INT'), False, False), (674, 'sub_4D7960', '004D7960', ('INT',), False, False), (675, 'sub_4D7BE0', '004D7BE0', ('INT', 'INT'), False, False), (676, 'sub_4D7D30', '004D7D30', ('INT', 'INT'), False, False), (677, 'sub_4D7E80', '004D7E80', ('INT',), False, False), (678, 'sub_4D7FE0', '004D7FE0', ('INT', 'INT'), False, False), (679, 'sub_4D8130', '004D8130', ('INT',), False, False), (680, 'sub_4D8290', '004D8290', ('INT', 'INT'), False, False), (681, 'sub_4D8510', '004D8510', ('INT', 'INT', 'INT', 'INT'), False, False), (682, 'sub_4D8770', '004D8770', ('INT', 'INT'), False, False), (683, 'sub_4D88C0', '004D88C0', (), False, False), (684, 'sub_4D89C0', '004D89C0', ('INT',), False, False), (685, 'sub_4D8B50', '004D8B50', (), False, False), (690, 'sub_4D8C50', '004D8C50', ('INT', 'INT'), False, False), (691, 'sub_4D8E50', '004D8E50', ('INT', 'INT'), False, False), (800, 'sub_4D8FB0', '004D8FB0', (), False, False), (801, 'sub_4D90B0', '004D90B0', (), False, False), (802, 'sub_4D91B0', '004D91B0', (), False, False), (803, 'sub_4D92B0', '004D92B0', ('INT',), False, False), (810, 'sub_4D9410', '004D9410', ('INT',), False, False), (811, 'sub_4D9530', '004D9530', ('INT',), False, False), (812, 'sub_4D9690', '004D9690', (), False, False), (813, 'sub_4D97E0', '004D97E0', ('INT',), False, False), (814, 'sub_4D9930', '004D9930', ('INT',), False, False), (815, 'sub_4D9AC0', '004D9AC0', (), False, False), (816, 'sub_4D9B40', '004D9B40', ('INT',), False, False), (817, 'sub_4D9E60', '004D9E60', ('INT', 'INT'), False, False), (818, 'sub_4D9FB0', '004D9FB0', ('INT', 'INT'), False, False), (819, 'sub_4DA100', '004DA100', ('INT',), False, False), (820, 'sub_4DA250', '004DA250', ('INT',), False, False), (821, 'sub_4DA3C0', '004DA3C0', ('INT',), False, False), (822, 'sub_4DA530', '004DA530', ('INT',), False, False), (823, 'sub_4DA6A0', '004DA6A0', ('INT',), False, False), (824, 'sub_4DA810', '004DA810', ('INT',), False, False)]


class ScriptError(Exception):
    pass


@dataclass(frozen=True)
class OpcodeDef:
    op: int
    handler: str
    handler_addr: str
    template: tuple[str, ...]
    dynamic: bool = False
    jump_helper: bool = False


def load_opcode_defs() -> dict[int, OpcodeDef]:
    return {
        op: OpcodeDef(op, handler, addr, tuple(template), dynamic, jump_helper)
        for op, handler, addr, template, dynamic, jump_helper in EMBEDDED_OPCODE_ROWS
    }


def read_u32(data: bytes, offset: int) -> int:
    if offset + 4 > len(data):
        raise ScriptError(f"u32 read overflow at 0x{offset:X}")
    return struct.unpack_from("<I", data, offset)[0]


def pack_u32(value: int) -> bytes:
    if value < 0:
        value &= 0xFFFFFFFF
    return struct.pack("<I", value)


def describe_encode_error(text: str, encoding: str, exc: UnicodeEncodeError) -> str:
    bad = text[exc.start : exc.end]
    points = ", ".join(f"U+{ord(ch):04X} {ch!r}" for ch in bad)
    return f"cannot encode text as {encoding} at char {exc.start}: {points}"


def encode_text(text: str, encoding: str = ENCODING) -> bytes:
    try:
        return text.encode(encoding)
    except UnicodeEncodeError as exc:
        raise ScriptError(describe_encode_error(text, encoding, exc)) from exc


def bytes_to_text(raw: bytes, encoding: str = ENCODING) -> str:
    if not raw:
        return ""
    try:
        return raw.decode(encoding)
    except UnicodeDecodeError:
        out: list[str] = []
        i = 0
        while i < len(raw):
            matched = False
            for size in (2, 1):
                part = raw[i : i + size]
                if not part:
                    continue
                try:
                    out.append(part.decode(encoding))
                    i += size
                    matched = True
                    break
                except UnicodeDecodeError:
                    continue
            if not matched:
                out.append(f"{{{{{raw[i]:02X}}}}}")
                i += 1
        return "".join(out)


PLACEHOLDER_RE = re.compile(r"\{\{([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2})*)\}\}")


def text_to_bytes(text: str, encoding: str = ENCODING) -> bytes:
    out = bytearray()
    pos = 0
    for match in PLACEHOLDER_RE.finditer(text):
        if match.start() > pos:
            out.extend(encode_text(text[pos : match.start()], encoding))
        out.extend(int(part, 16) for part in match.group(1).split(":"))
        pos = match.end()
    if pos < len(text):
        out.extend(encode_text(text[pos:], encoding))
    return bytes(out)


def read_int(data: bytes, offset: int) -> tuple[dict[str, Any], int]:
    if offset + 12 > len(data):
        raise ScriptError(f"INT overflow at 0x{offset:X}")
    return (
        {
            "kind": "INT",
            "offset": offset,
            "flag": data[offset],
            "pad": list(data[offset + 1 : offset + 4]),
            "id": read_u32(data, offset + 4),
            "value": read_u32(data, offset + 8),
        },
        offset + 12,
    )


def write_int(param: dict[str, Any]) -> bytes:
    pad = bytes(param.get("pad", [0, 0, 0]))
    if len(pad) != 3:
        raise ScriptError("INT pad must contain exactly 3 bytes")
    return bytes([int(param["flag"]) & 0xFF]) + pad + pack_u32(int(param["id"])) + pack_u32(int(param["value"]))


def read_str(data: bytes, offset: int, encoding: str = ENCODING) -> tuple[dict[str, Any], int]:
    if offset + 9 > len(data):
        raise ScriptError(f"STR header overflow at 0x{offset:X}")
    size = read_u32(data, offset + 5)
    end = offset + 9 + size
    if size > 0x40000 or end > len(data):
        raise ScriptError(f"bad STR size {size} at 0x{offset:X}")
    raw = data[offset + 9 : end]
    return (
        {
            "kind": "STR",
            "offset": offset,
            "flag": data[offset],
            "id": read_u32(data, offset + 1),
            "size": size,
            "text": bytes_to_text(raw, encoding),
        },
        end,
    )


def write_str(param: dict[str, Any], encoding: str = ENCODING) -> bytes:
    raw = text_to_bytes(param.get("text", ""), encoding)
    return bytes([int(param["flag"]) & 0xFF]) + pack_u32(int(param["id"])) + pack_u32(len(raw)) + raw


def read_lbl(data: bytes, offset: int) -> tuple[dict[str, Any], int]:
    if offset + 40 > len(data):
        raise ScriptError(f"LBL overflow at 0x{offset:X}")
    values = [read_u32(data, offset + i) for i in range(0, 40, 4)]
    return {"kind": "LBL", "offset": offset, "values": values}, offset + 40


def write_lbl(param: dict[str, Any]) -> bytes:
    values = param["values"]
    if len(values) != 10:
        raise ScriptError("LBL must contain 10 u32 values")
    return b"".join(pack_u32(int(value)) for value in values)


def parse_operands(
    op: int,
    data: bytes,
    offset: int,
    opcode_defs: dict[int, OpcodeDef],
    encoding: str = ENCODING,
) -> tuple[list[dict[str, Any]], int]:
    params: list[dict[str, Any]] = []

    if op == 31:
        p0, offset = read_int(data, offset)
        p1, offset = read_int(data, offset)
        p2, offset = read_int(data, offset)
        params.extend([p0, p1, p2])
        str_count = p1["value"]
        int_count = p2["value"]
        if str_count > 64 or int_count > 512:
            raise ScriptError(f"op31 unreasonable list counts: {str_count}, {int_count}")
        for _ in range(str_count):
            param, offset = read_str(data, offset, encoding)
            params.append(param)
        for _ in range(int_count):
            param, offset = read_int(data, offset)
            params.append(param)
        return params, offset

    if op in (22, 23):
        p0, offset = read_int(data, offset)
        p1, offset = read_int(data, offset)
        params.extend([p0, p1])
        lbl_count = p1["value"]
        if lbl_count > 512:
            raise ScriptError(f"op{op} unreasonable LBL count: {lbl_count}")
        for _ in range(lbl_count):
            param, offset = read_lbl(data, offset)
            params.append(param)
        return params, offset

    for kind in opcode_defs[op].template:
        if kind == "INT":
            param, offset = read_int(data, offset)
        elif kind == "STR":
            param, offset = read_str(data, offset, encoding)
        elif kind == "LBL":
            param, offset = read_lbl(data, offset)
        else:
            raise ScriptError(f"unknown operand kind {kind}")
        params.append(param)
    return params, offset


def parse_script(data: bytes, opcode_defs: dict[int, OpcodeDef], encoding: str = ENCODING) -> list[dict[str, Any]]:
    offset = 0
    instructions: list[dict[str, Any]] = []
    while offset < len(data):
        start = offset
        if offset + 4 > len(data):
            raise ScriptError(f"trailing bytes at 0x{offset:X}")
        op = read_u32(data, offset)
        if op not in opcode_defs:
            raise ScriptError(f"unknown op {op} at 0x{start:X}")
        params, offset = parse_operands(op, data, offset + 4, opcode_defs, encoding)
        instructions.append({"offset": start, "op": op, "handler": opcode_defs[op].handler, "params": params, "size": offset - start})
    return instructions


def instruction_size(inst: dict[str, Any], encoding: str = ENCODING) -> int:
    size = 4
    for param in inst.get("params", []):
        if param["kind"] == "INT":
            size += 12
        elif param["kind"] == "STR":
            size += 9 + len(text_to_bytes(param.get("text", ""), encoding))
        elif param["kind"] == "LBL":
            size += 40
        else:
            raise ScriptError(f"unknown param kind {param['kind']}")
    return size


def build_relocation_map(instructions: list[dict[str, Any]], encoding: str = ENCODING) -> dict[int, int]:
    old_to_new: dict[int, int] = {}
    new_offset = 0
    for inst in instructions:
        old_to_new[int(inst["offset"])] = new_offset
        new_offset += instruction_size(inst, encoding)
    old_to_new[sum(int(inst["size"]) for inst in instructions)] = new_offset
    return old_to_new


def relocate_internal_targets(instructions: list[dict[str, Any]], old_to_new: dict[int, int]) -> None:
    for inst in instructions:
        if int(inst["op"]) not in INTERNAL_JUMP_OPS:
            continue
        for param in inst.get("params", []):
            if param["kind"] != "LBL":
                continue
            target = int(param["values"][0])
            if target not in old_to_new:
                raise ScriptError(f"jump target 0x{target:X} from op {inst['op']} at 0x{inst['offset']:X} is not an instruction boundary")
            param["values"][0] = old_to_new[target]


def assemble_script(instructions: list[dict[str, Any]], encoding: str = ENCODING, relocate: bool = True) -> bytes:
    if relocate:
        relocate_internal_targets(instructions, build_relocation_map(instructions, encoding))
    out = bytearray()
    for inst in instructions:
        out.extend(pack_u32(int(inst["op"])))
        for param in inst.get("params", []):
            if param["kind"] == "INT":
                out.extend(write_int(param))
            elif param["kind"] == "STR":
                out.extend(write_str(param, encoding))
            elif param["kind"] == "LBL":
                out.extend(write_lbl(param))
            else:
                raise ScriptError(f"unknown param kind {param['kind']}")
    return bytes(out)


def normalize_rel(path: Path) -> str:
    return "\\".join(path.parts)


def split_rel(rel: str) -> Path:
    return Path(*rel.replace("/", "\\").split("\\"))


def common_base(inputs: Iterable[Path]) -> Path:
    resolved = [p.resolve() for p in inputs]
    if len(resolved) == 1:
        return resolved[0] if resolved[0].is_dir() else resolved[0].parent
    return Path(os.path.commonpath([str(p) for p in resolved]))


def iter_script_files(inputs: list[Path]) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        if item.is_file():
            files.append(item)
        elif item.is_dir():
            files.extend(path for path in item.rglob("*") if path.is_file())
        else:
            raise ScriptError(f"input path not found: {item}")
    return sorted(set(files), key=lambda p: str(p))


def asm_name_for_rel(rel: Path) -> str:
    return "__".join(rel.parts) + ".asm.json"


def json_name_for_rel(rel: Path) -> str:
    return "__".join(rel.parts) + ".json"


def make_asm(path: Path, base: Path, opcode_defs: dict[int, OpcodeDef], encoding: str = ENCODING) -> dict[str, Any]:
    data = path.read_bytes()
    instructions = parse_script(data, opcode_defs, encoding)
    rel = path.resolve().relative_to(base.resolve())
    return {
        "format": "mnv-asm-json-v1",
        "encoding": encoding,
        "relative_path": normalize_rel(rel),
        "source_size": len(data),
        "instructions": instructions,
    }


def load_asm(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_b31_message(text: str) -> str:
    return text.replace("\r\n", "").replace("\n", "")


def extract_text_entries(path: Path, base: Path, instructions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entries: list[dict[str, Any]] = []
    meta_entries: list[dict[str, Any]] = []
    rel = normalize_rel(path.resolve().relative_to(base.resolve()))
    for inst_index, inst in enumerate(instructions):
        if inst["op"] != TEXT_OPCODE:
            continue
        str_params = [p for p in inst["params"] if p["kind"] == "STR"]
        if len(str_params) < 2 or not str_params[TEXT_MESSAGE_PARAM].get("text"):
            continue
        name = str_params[TEXT_NAME_PARAM].get("text", "")
        raw_message = str_params[TEXT_MESSAGE_PARAM].get("text", "")
        message = clean_b31_message(raw_message)
        entry_id = len(entries)
        entry: dict[str, Any] = {"id": entry_id}
        if name:
            entry["name"] = name
        entry["pre_jp"] = message
        entry["message"] = message
        entries.append(entry)

        meta: dict[str, Any] = {
            "id": entry_id,
            "file": rel,
            "kind": "dialog" if name else "narration",
            "scheme": "B3.1",
            "op": inst["op"],
            "inst_index": inst_index,
            "inst_offset": inst["offset"],
            "message_param_index": TEXT_MESSAGE_PARAM,
            "message_param_offset": str_params[TEXT_MESSAGE_PARAM]["offset"],
            "orig_message_raw": raw_message,
            "orig_message_size": str_params[TEXT_MESSAGE_PARAM]["size"],
            "removed_newlines": raw_message != message,
        }
        if name:
            meta["name_param_index"] = TEXT_NAME_PARAM
            meta["name_param_offset"] = str_params[TEXT_NAME_PARAM]["offset"]
            meta["orig_name_raw"] = name
            meta["orig_name_size"] = str_params[TEXT_NAME_PARAM]["size"]
        meta_entries.append(meta)
    return entries, meta_entries


def verify_inputs(inputs: list[Path], opcode_defs: dict[int, OpcodeDef], encoding: str, log_path: Path | None) -> dict[str, Any]:
    files = iter_script_files(inputs)
    used_ops: set[int] = set()
    total_instructions = 0
    failures: list[dict[str, Any]] = []
    for path in files:
        try:
            data = path.read_bytes()
            instructions = parse_script(data, opcode_defs, encoding)
            rebuilt = assemble_script(instructions, encoding)
            if rebuilt != data:
                failures.append({"file": str(path), "error": "roundtrip mismatch"})
            used_ops.update(int(inst["op"]) for inst in instructions)
            total_instructions += len(instructions)
        except Exception as exc:
            failures.append({"file": str(path), "error": str(exc)})
    result = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "files": len(files),
        "failures": failures,
        "total_instructions": total_instructions,
        "switch_opcodes": len(opcode_defs),
        "used_opcodes": sorted(used_ops),
        "used_opcode_count": len(used_ops),
        "unknown_opcodes": 0 if not failures else None,
        "roundtrip": "byte-identical" if not failures else "failed",
    }
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def write_analysis(opcode_defs: dict[int, OpcodeDef], out_path: Path) -> None:
    lines = [
        "# M no Violet VM Analysis",
        "",
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
        "- Command ID: little-endian u32 at each instruction start.",
        "- INT param: 12 bytes, flag u8 + 3 pad bytes + id u32 + value u32.",
        "- STR param: flag u8 + id u32 + byte length u32 + cp932 bytes.",
        "- LBL param: 10 little-endian u32 values, 40 bytes total.",
        "- Dynamic params: op31 uses INT[1].value as string-list count and INT[2].value as int-list count; op22/op23 use INT[1].value as LBL count.",
        "",
        "## Opcode Table",
        "",
        "| OP | Handler | Template | Dynamic | Jump Helper |",
        "|---:|---|---|---|---|",
    ]
    for op in sorted(opcode_defs):
        spec = opcode_defs[op]
        template = ",".join(spec.template) if spec.template else "-"
        lines.append(f"| {op} | `{spec.handler}` | `{template}` | {str(spec.dynamic).lower()} | {str(spec.jump_helper).lower()} |")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_translation_entries(json_dir: Path) -> dict[str, list[tuple[dict[str, Any], dict[str, Any]]]]:
    by_file: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for path in sorted(json_dir.glob("*.json")):
        if path.name.startswith("_") or path.name.endswith(".meta.json"):
            continue
        entries = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            raise ScriptError(f"translation JSON must be a list: {path}")
        meta_path = path.with_name(path.name + ".meta.json")
        meta_payload = json.loads(meta_path.read_text(encoding="utf-8"))
        file_name = meta_payload.get("file")
        if not file_name:
            raise ScriptError(f"meta without file: {meta_path}")
        meta_by_id = {int(item["id"]): item for item in meta_payload.get("entries", [])}
        for entry in entries:
            entry_id = int(entry["id"])
            if entry_id not in meta_by_id:
                raise ScriptError(f"missing meta for id {entry_id} in {path}")
            by_file.setdefault(file_name, []).append((entry, meta_by_id[entry_id]))
    return by_file


def apply_entries_to_instructions(instructions: list[dict[str, Any]], entries: list[tuple[dict[str, Any], dict[str, Any]]]) -> int:
    changed = 0
    for entry, meta in entries:
        text = entry.get("message") or entry.get("pre_jp")
        inst_index = int(meta["inst_index"])
        param_index = int(meta["message_param_index"])
        expected_offset = int(meta["inst_offset"])
        if inst_index < 0 or inst_index >= len(instructions):
            raise ScriptError(f"bad inst_index in {entry.get('id')}")
        inst = instructions[inst_index]
        if int(inst["offset"]) != expected_offset:
            raise ScriptError(f"offset mismatch in {entry.get('id')}")
        str_params = [p for p in inst["params"] if p["kind"] == "STR"]
        if param_index < 0 or param_index >= len(str_params):
            raise ScriptError(f"bad message_param_index in {entry.get('id')}")
        if str_params[param_index].get("text") != text:
            str_params[param_index]["text"] = text
            changed += 1
        if "name" in entry and "name_param_index" in meta:
            name_index = int(meta["name_param_index"])
            if name_index < 0 or name_index >= len(str_params):
                raise ScriptError(f"bad name_param_index in {entry.get('id')}")
            name_text = entry.get("name") or ""
            if str_params[name_index].get("text") != name_text:
                str_params[name_index]["text"] = name_text
                changed += 1
    return changed


def single_byte_findings(text: str, encoding: str = ENCODING) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    byte_pos = 0
    for char_index, ch in enumerate(text):
        raw = text_to_bytes(ch, encoding)
        if len(raw) == 1:
            b = raw[0]
            kind = "control" if b < 0x20 or b == 0x7F else "single-byte"
            findings.append({"char_index": char_index, "byte_offset": byte_pos, "char": ch, "byte": f"0x{b:02X}", "kind": kind})
        byte_pos += len(raw)
    return findings


def scan_json_dir(json_dir: Path, encoding: str = ENCODING, log_path: Path | None = None) -> dict[str, Any]:
    total_entries = 0
    total_findings = 0
    control_findings = 0
    samples: list[dict[str, Any]] = []
    newline_hits: list[dict[str, Any]] = []
    for path in sorted(json_dir.glob("*.json")):
        if path.name.startswith("_") or path.name.endswith(".meta.json"):
            continue
        entries = json.loads(path.read_text(encoding="utf-8"))
        for entry in entries:
            total_entries += 1
            for field in ("name", "pre_jp", "message"):
                if field not in entry:
                    continue
                text = entry[field]
                if "\n" in text or "\r" in text:
                    newline_hits.append({"file": path.name, "id": entry.get("id"), "field": field})
                findings = single_byte_findings(text, encoding)
                total_findings += len(findings)
                control_findings += sum(1 for item in findings if item["kind"] == "control")
                for item in findings[:5]:
                    if len(samples) >= 50:
                        break
                    sample = {"file": path.name, "id": entry.get("id"), "field": field}
                    sample.update(item)
                    samples.append(sample)
    result = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "entries_scanned": total_entries,
        "single_byte_hits": total_findings,
        "control_code_hits": control_findings,
        "main_json_newline_hits": len(newline_hits),
        "samples": samples,
        "newline_samples": newline_hits[:50],
    }
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def cmd_analyze(args: argparse.Namespace) -> None:
    defs = load_opcode_defs()
    out = Path(args.output)
    write_analysis(defs, out)
    print(f"[OK] wrote {out} ({len(defs)} opcodes)")


def cmd_verify(args: argparse.Namespace) -> None:
    defs = load_opcode_defs()
    inputs = [Path(p) for p in args.inputs]
    log_path = Path(args.log) if args.log else ROOT / "logs" / f"mnv_script_verify_{datetime.now():%Y%m%d_%H%M%S}.json"
    result = verify_inputs(inputs, defs, args.encoding, log_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"log: {log_path}")
    if result["failures"]:
        raise SystemExit(1)


def cmd_disasm(args: argparse.Namespace) -> None:
    defs = load_opcode_defs()
    inputs = [Path(p) for p in args.inputs]
    base = Path(args.base).resolve() if args.base else common_base(inputs)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    failures: list[dict[str, str]] = []
    for path in iter_script_files(inputs):
        try:
            asm = make_asm(path, base, defs, args.encoding)
            rel = split_rel(asm["relative_path"])
            (out_dir / asm_name_for_rel(rel)).write_text(json.dumps(asm, ensure_ascii=False, indent=2), encoding="utf-8")
            written += 1
        except Exception as exc:
            failures.append({"file": str(path), "error": str(exc)})
    summary = {"format": "mnv-asm-manifest-v1", "base": str(base), "files": written, "failures": failures}
    (out_dir / "_asm_manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


def cmd_asm(args: argparse.Namespace) -> None:
    asm_dir = Path(args.asm_dir)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for path in sorted(asm_dir.glob("*.asm.json")):
        asm = load_asm(path)
        rel = split_rel(asm["relative_path"])
        target = out_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(assemble_script(asm["instructions"], asm.get("encoding", args.encoding)))
        written += 1
    print(json.dumps({"asm_files": written, "output": str(out_dir)}, ensure_ascii=False, indent=2))


def cmd_extract(args: argparse.Namespace) -> None:
    defs = load_opcode_defs()
    inputs = [Path(p) for p in args.inputs]
    base = Path(args.base).resolve() if args.base else common_base(inputs)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    entries_total = 0
    files_with_text = 0
    failures: list[dict[str, str]] = []
    for path in iter_script_files(inputs):
        try:
            instructions = parse_script(path.read_bytes(), defs, args.encoding)
            entries, meta_entries = extract_text_entries(path, base, instructions)
            if not entries:
                continue
            rel = path.resolve().relative_to(base.resolve())
            json_name = json_name_for_rel(rel)
            meta_payload = {"file": normalize_rel(rel), "format": "mnv-text-meta-b3.1-v1", "encoding": args.encoding, "entries": meta_entries}
            (out_dir / json_name).write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
            (out_dir / (json_name + ".meta.json")).write_text(json.dumps(meta_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            entries_total += len(entries)
            files_with_text += 1
        except Exception as exc:
            failures.append({"file": str(path), "error": str(exc)})
    summary = {"time": datetime.now().isoformat(timespec="seconds"), "scheme": "B3.1", "base": str(base), "files_with_text": files_with_text, "entries": entries_total, "text_op": TEXT_OPCODE, "message_param": TEXT_MESSAGE_PARAM, "failures": failures}
    (out_dir / "_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


def cmd_inject(args: argparse.Namespace) -> None:
    defs = load_opcode_defs()
    json_dir = Path(args.json_dir)
    inputs = [Path(p) for p in args.inputs]
    base = Path(args.base).resolve() if args.base else common_base(inputs)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.copy_base:
        if not base.is_dir():
            raise ScriptError("--copy-base requires --base to be a directory")
        for source in (p for p in base.rglob("*") if p.is_file()):
            rel = source.relative_to(base)
            target = out_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
    by_file = load_translation_entries(json_dir)
    changed_files = 0
    changed_entries = 0
    for rel, entries in by_file.items():
        source = base / split_rel(rel)
        if not source.exists():
            raise ScriptError(f"script file not found: {source}")
        instructions = parse_script(source.read_bytes(), defs, args.encoding)
        changed = apply_entries_to_instructions(instructions, entries)
        target = out_dir / split_rel(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(assemble_script(instructions, args.encoding, relocate=True))
        changed_files += 1
        changed_entries += changed
    summary = {"time": datetime.now().isoformat(timespec="seconds"), "source_json": str(json_dir), "base": str(base), "output": str(out_dir), "files": changed_files, "changed_entries": changed_entries, "relocation": "internal LBL[0] targets for op20/op21/op22/op24"}
    (out_dir / "_inject_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_scan(args: argparse.Namespace) -> None:
    log_path = Path(args.log) if args.log else ROOT / "logs" / f"mnv_single_byte_scan_{datetime.now():%Y%m%d_%H%M%S}.json"
    result = scan_json_dir(Path(args.json_dir), args.encoding, log_path)
    printable = {k: v for k, v in result.items() if k not in ("samples", "newline_samples")}
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    print(f"log: {log_path}")
    if args.fail_on_hit and (result["single_byte_hits"] or result["main_json_newline_hits"]):
        raise SystemExit(1)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="M no Violet script disassembler/assembler/text tools")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("analyze", help="write the frozen opcode table as Markdown")
    p.add_argument("-o", "--output", default=str(ROOT / "vm_analysis.md"))
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("verify", help="parse and rebuild every file under one or more folders")
    p.add_argument("inputs", nargs="+")
    p.add_argument("--encoding", default=ENCODING)
    p.add_argument("--log")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("disasm", help="disassemble folders to an asm-json folder")
    p.add_argument("inputs", nargs="+")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--base", help="base directory used for relative paths")
    p.add_argument("--encoding", default=ENCODING)
    p.set_defaults(func=cmd_disasm)

    p = sub.add_parser("asm", help="assemble an asm-json folder back to script files")
    p.add_argument("asm_dir")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--encoding", default=ENCODING)
    p.set_defaults(func=cmd_asm)

    p = sub.add_parser("extract", help="extract B3.1 translation JSON and meta JSON from folders")
    p.add_argument("inputs", nargs="+")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--base", help="base directory used for relative paths")
    p.add_argument("--encoding", default=ENCODING)
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("inject", help="inject translated JSON into scripts and relocate internal jumps")
    p.add_argument("json_dir")
    p.add_argument("inputs", nargs="+")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--base", help="base directory used for relative paths")
    p.add_argument("--copy-base", action="store_true", help="copy the whole base directory before overlaying injected scripts")
    p.add_argument("--encoding", default=ENCODING)
    p.set_defaults(func=cmd_inject)

    p = sub.add_parser("scan", help="scan extracted JSON for suspicious single-byte CP932 characters")
    p.add_argument("json_dir")
    p.add_argument("--encoding", default=ENCODING)
    p.add_argument("--log")
    p.add_argument("--fail-on-hit", action="store_true")
    p.set_defaults(func=cmd_scan)
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except ScriptError as exc:
        raise SystemExit(f"[ERROR] {exc}") from exc


if __name__ == "__main__":
    main()
