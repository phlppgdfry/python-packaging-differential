"""Inputs: hand-picked edge cases from PEP 440 / PEP 508 plus seeded random versions."""

import random

# The marker environment every implementation evaluates against (a CPython 3.12.4 Linux box).
ENV = {
    "implementation_name": "cpython",
    "implementation_version": "3.12.4",
    "os_name": "posix",
    "platform_machine": "x86_64",
    "platform_python_implementation": "CPython",
    "platform_release": "6.8.0-45-generic",
    "platform_system": "Linux",
    "platform_version": "#45-Ubuntu SMP PREEMPT_DYNAMIC",
    "python_full_version": "3.12.4",
    "python_version": "3.12",
    "sys_platform": "linux",
    "extra": "",
}
random.seed(1754)

# ---------------------------------------------------------------- inputs
VERSIONS = """
1.0|1.0.0|1|01.02|1.0.0.0.0|0|00|1!2.0|0!1.0|v1.0|V1.0| 1.0|1.0 |\t1.0\n|1.0RC1|1.0rc1|1.0-rc.1|1.0_rc_1|1.0.rc1|1.0c1|1.0pre1|1.0preview1
|1.0alpha1|1.0beta|1.0a|1.0b2|1.0-1|1.0.post|1.0-r1|1.0rev1|1.0.post1|1.0post1|1.0-post-1|1.0.dev|1.0dev1|1.0.dev0|1.0-dev-3|1.0a1.post2.dev3
|1.0.post1.dev1|1.0+abc.5|1.0+ABC|1.0+a-b_c|1.0+|1.0+.a|1.0+a..b|1.0+01|1.0+1.01|1.0+_a|.1|1.|1..0||1.0a1b2|1.0.post1.post2|1.0-1-1
|1.99999999999999999999|18446744073709551616.0|1.0.18446744073709551615|１.0|1.٠|1.0 | 1.0|1.0 |1,0|1.0.*|1.0a-1|1.0-|1.0_|1.0.
|1!|!1.0|1!1!1.0|1.0+local+again|1.0POST1|1.0DEV1|1.0Rc1|1.0+Ünicode|1.0+a.b.c.d.e.f.g|1.0.0a0|1.0.0.dev0+local|2.0.0-ALPHA-1|1.0r|1.0-r|1.0.r1
""".replace("\n", "").split("|")

FRAG = ["1", "0", "01", "2", ".", "a", "b", "rc", "c", "post", "dev", "-", "_", "+", "!", "local", "r", "pre", "1.2", "  "]


def fuzz_versions(n):
    out = set()
    for _ in range(n):
        out.add("".join(random.choice(FRAG) for _ in range(random.randint(1, 6))))
    return sorted(out)


SPECS = """
==1.0|==1.0.*|!=1.0.*|==1.*|==1.0.0.*|~=1.0|~=1.0.0|~=1|>=1.0|>1.0|<1.0|<=1.0|===1.0|===foobar|>=1.0,<2.0|>= 1.0 , < 2.0|>1.0.post1|>1.0.dev0
|<1.0.dev0|<1.0rc1|>1.0rc1|==1.0+local|!=1.0+local|<=1.0+local|>=1.0+local|==1.0.*+local|== 1.0 .*|==1.0.*.dev1|~=1.0.*|==1.0.post1.*
|>=1!1.0|==v1.0|~=1.0a1|>=1.0a1|<2.0a1|>1.0+local|==1.0rc1.*|!=1.0rc1|>=1.0,!=1.5.*|<= 1.0|==|>=||,|>=1.0,|1.0|=1.0|=>1.0|~1.0
""".replace("\n", "").split("|")

PROBE_VERSIONS = ["0.9", "1.0", "1.0.0", "1.0.1", "1.0.post1", "1.0.post1.dev1", "1.0.dev0", "1.0a1", "1.0rc1", "1.0+local", "1.0+other",
                  "1.0.0+local", "1.1", "1.5.2", "1.99", "2.0", "2.0a1", "2.0.dev0", "1!1.0", "1!0.5", "1.0.0.0.1", "0.9.post1"]

MARKERS = """
python_version >= "3.8"|python_version > "3.12"|python_version < "3.12.1"|python_version <= "3.12"|python_version == "3.12"|python_version == "3.12.0"
|python_version != "3.12.*"|python_version == "3.*"|python_version == "3.1*"|python_version ~= "3.10"|python_version ~= "3"|python_version === "3.12"
|python_full_version == "3.12.*"|python_full_version >= "3.12.4rc1"|python_full_version > "3.12.4.dev0"|python_full_version < "3.12.4.post1"
|python_full_version == "3.12.4+local"|python_full_version ~= "3.12.0"|"3.8" < python_version|"3.13" > python_version|"3.12" == python_version
|python_version in "3.10 3.11 3.12"|python_version not in "3.1 3.2"|"3.1" in python_version|"2" in python_version|python_version in "3.12.4"
|platform_release >= "6.0"|platform_release > "6.8.0"|platform_release == "6.8.0-45-generic"|platform_release < "7"|platform_release ~= "6.8"
|platform_version >= "#45"|platform_machine == "x86_64"|platform_machine == "X86_64"|platform_machine in "x86_64 aarch64"|"x86" in platform_machine
|sys_platform == "linux" and python_version >= "3.8"|sys_platform == "win32" or python_version >= "3.8"|sys_platform == "linux" or os_name == "nt" and python_version < "3"
|(sys_platform == "linux" or os_name == "nt") and python_version < "3"|implementation_version >= "3.12"|implementation_name == "CPython"
|python_version > 'abc'|python_version == 'abc'|platform_system == 'Linux'|platform_system != 'linux'|os_name < "posix"|os_name >= "posix"
|extra == "test"|extra != "test"|python_version >= "3.8" and extra == "test"|python_version<'3.13'|python_version<"3.13"and os_name=="posix"
|python_version >= "3.8" and (os_name == "posix")|((python_version >= "3.8"))|python_version >= " 3.8"|python_version >= "3.8 "|python_version>="3.8.*"
|python_version == "3.12.*.*"|python_version >= "1!3.8"|python_version ~= "3.12.*"|python_version == "3"|python_full_version == "3.12"|python_full_version != "3.12"
|"linux" == sys_platform|"cpython" == implementation_name|"3.12" != python_version|'3.0' <= python_version|"3.13" >= python_full_version|platform_release in "6.8.0-45-generic-extra"|platform_release not in "6.8"|python_version < "3.12.0a1"|python_full_version >= "3.12.4a0"
""".replace("\n", "").split("|")


