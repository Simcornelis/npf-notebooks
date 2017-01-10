from subprocess import Popen, PIPE
from subprocess import TimeoutExpired
import os
import sys
import numpy as np
import signal

from typing import Dict, List

from src.section import *


class Run:
    def __init__(self, variables):
        self.variables = variables

    def format_variables(self, hide={}):
        s = []
        for k, v in self.variables.items():
            if k in hide: continue
            if type(v) is tuple:
                s.append('%s = %s' % (k, v[1]))
            else:
                s.append('%s = %s' % (k, v))
        return ', '.join(s)

    def print_variable(self, k):
        v = self.variables[k]
        if type(v) is tuple:
            return v[1]
        else:
            return v

    def copy(self):
        newrun = Run(self.variables.copy())
        return newrun

    def __eq__(self, o):
        for k, v in self.variables.items():
            if not k in o.variables:
                return False
            ov = o.variables[k]
            if type(v) is tuple:
                v = v[1]
            if type(ov) is tuple:
                ov = ov[1]
            if not v == ov:
                return False
        return True

    def __hash__(self):
        n = 0
        for k, v in self.variables.items():
            if type(v) is tuple:
                n += v[1].__hash__()
            else:
                n += v.__hash__()
            n += k.__hash__()
        return n

    def __repr__(self):
        return "Run(" + self.format_variables() + ")"

    def __lt__(self, o):
        for k, v in self.variables.items():
            if not k in o.variables: return False
            if v < o.variables[k]:
                return True
            if v > o.variables[k]:
                return False
        return False


Dataset = Dict[Run, List]


class Testie:
    def __init__(self, testie_path, quiet=False, show_full=False, tags=[]):
        self.sections = []
        self.files = []
        self.scripts = []
        self.filename = os.path.basename(testie_path)
        self.quiet = quiet
        self.show_full = show_full
        self.appdir = os.path.dirname(os.path.abspath(sys.argv[0])) + "/"
        self.tags = tags
        section = ''

        f = open(testie_path, 'r')
        for line in f:
            if line.startswith("#"):
                continue
            elif line.startswith("%"):
                result = line[1:].split(' ')
                section = SectionFactory.build(self, result)
                self.sections.append(section)
            elif not section:
                raise Exception("Bad syntax, file must start by a section");
            else:
                section.content += line

        if not hasattr(self, "info"):
            self.info = Section("info")
            self.info.content = self.filename
            self.sections.append(self.info)

        if not hasattr(self, "stdin"):
            self.stdin = Section("stdin")
            self.sections.append(self.stdin)

        if not hasattr(self, "variables"):
            self.variables = SectionVariable()
            self.sections.append(self.variables)

        for section in self.sections:
            section.finish(self)

    def test_tags(self):
        missings = []
        for tag in self.config.get_list("require_tags"):
            if not tag in self.tags:
                missings.append(tag)
        return missings

    def create_files(self, v):
        for s in self.files:
            f = open(s.filename, "w")
            p = s.content
            for k, v in v.items():
                if type(v) is tuple:
                    p = p.replace("$" + k, str(v[0]))
                else:
                    p = p.replace("$" + k, str(v))
            f.write(p)
            f.close()

    def cleanup(self):
        for s in self.files:
            os.remove(s.filename)

    def execute(self, build, v, n_runs=1, n_retry=0):
        self.create_files(v)
        results = []
        for i in range(n_runs):
            output = ''
            err = ''
            for script in self.scripts:
                if len(self.scripts) > 1:
                    output += "Output of script for %s" % script.slave
                    err += "Output of script for %s" % script.slave

                for i_try in range(n_retry + 1):
                    p = Popen(script.content, stdin=PIPE, stdout=PIPE, stderr=PIPE, shell=True, preexec_fn=os.setsid,
                              env={"PATH": self.appdir + build.repo.reponame + "/build/bin:" + os.environ["PATH"]})
                    pid = p.pid
                    try:
                        s_output, s_err = [x.decode() for x in
                                           p.communicate(self.stdin.content, timeout=self.config["timeout"])]
                        output += s_output
                        err += s_err
                        break
                    except TimeoutExpired:
                        print("Test expired")
                        p.terminate()
                        p.kill()
                        os.killpg(os.getpgid(pid), signal.SIGTERM)
                        if (i_try == n_retry):
                            return False, "Timeout expired.", ""

            nr = re.search("RESULT ([0-9.]+)", output.strip())
            if nr:
                n = float(nr.group(1))
                results.append(n)
            else:
                print("Could not find result !")
                print("stdout:")
                print(output)
                print("stderr:")
                print(err)
                return False, output, err

        self.cleanup()
        return results, output, err

    def has_all(self, prev_results=None):
        if prev_results is None:
            return False
        for variables in self.variables:
            run = Run(variables)

            if prev_results and run in prev_results:
                results = prev_results[run]
                if not results or results is None or (len(results) < self.config["n_runs"]):
                    return False
            else:
                return False
        return True

    def execute_all(self, build, prev_results:Dataset=None, do_test=True) -> Dataset:
        """Execute script for all variables combinations
        :param build: A build object
        :param prev_results: Previous set of result for the same build to update or retrieve
        :return: Dataset(Dict of variables as key and arrays of results as value)
        """
        all_results = {}
        for variables in self.variables:
            run = Run(variables)
            if not self.quiet:
                print(run.format_variables(self.config["var_hide"]))
            if prev_results and run in prev_results:
                results = prev_results[run]
                if not results:
                    results = []
            else:
                results = []
            n_runs = self.config["n_runs"] - len(results)
            if n_runs > 0 and do_test:
                nresults, output, err = self.execute(build, variables, n_runs, self.config["n_retry"])
                if nresults:
                    if self.show_full:
                        print("stdout:")
                        print(output)
                        print("stderr:")
                        print(err)
                    results += nresults
            if results:
                if not self.quiet:
                    print(results)
                all_results[run] = results
            else:
                all_results[run] = None
        return all_results

    def get_title(self):
        if "title" in self.config:
            title = self.config["title"]
        elif hasattr(self, "info"):
            title = self.info.content.strip().split('\n', 1)[0]
        else:
            title = self.filename
        return title

    def reject_outliers(self, data):
        m = self.config["accept_outliers_mult"]
        mean = np.mean(data)
        std = np.std(data)
        data = data[abs(data - mean) <= m * std]
        return data

    def expand_folder(testie_path, quiet=True, tags=[], show_full=False) -> List:
        testies = []
        if os.path.isfile(testie_path):
            testie = Testie(testie_path, quiet=quiet, show_full=show_full, tags=tags)
            testies.append(testie)
        else:
            for root, dirs, files in os.walk(testie_path):
                for file in files:
                    if file.endswith(".conf"):
                        testie = Testie(os.path.join(root, file), quiet=quiet, show_full=show_full, tags=tags)
                        missing_tags = testie.test_tags()
                        if len(missing_tags) > 0:
                            if not quiet:
                                print(
                                    "Passing testie %s as it lacks tags %s" % (testie.filename, ','.join(missing_tags)))
                            continue
                        testies.append(testie)

        return testies