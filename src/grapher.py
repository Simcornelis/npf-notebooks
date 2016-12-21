import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import math
graphcolor = ['b','g','r','c','m','y']

class Grapher:
    def __init__(self):
        self.scripts = set()

    def config(self, var, default=None):
        for script in self.scripts:
            if var in script.config:
                return script.config[var]
        return default

    def scriptconfig(self, var, key, default):
        for script in self.scripts:
            if var in script.config:
                if key in script.config[var]:
                    return script.config[var][key]
                else:
                    return default
        return None


    def var_name(self, key):
        return self.scriptconfig("var_names",key,key);

    def var_unit(self, key):
        return self.scriptconfig("var_unit",key,default=None);

    def bits(self, x, pos):
        if (x > 1000000000):
            return "%.2f GB/s" % (x/1000000000)
        elif (x > 1000000):
            return "%.2f MB/s" % (x/1000000)
        elif (x > 1000):
            return "%.2f KB/s" % (x/1000)
        else:
            return "%.2f B/s" % (x)

    def graph(self,filename, title=False, series=[], graph_allvariables=False):
        """series is a list of triplet (script,build,results) where
        result is the output of a script.execute_all()"""
        vars_values = {}
        vars_all = set()
        uuids=[]

        ymin,ymax=(float('inf'),0)

        #Data transformation
        for i,(script,build,all_results) in enumerate(series):
            uuids.append(build.uuid)
            self.scripts.add(script)
            for run,results in all_results.items():
                if results:
                    ymax = max(ymax, max(results))
                    ymin = min(ymin, min(results))
                if i == 0 or graph_allvariables:
                    vars_all.add(run)
                    for k,v in run.variables.items():
                        vars_values.setdefault(k,set()).add(v)
        vars_all = list(vars_all)
        vars_all.sort()
        is_multiscript = len(self.scripts) > 1

        #self.ydiv = math.exp(math.log(ymax,10),10)

        dyns = []

        for k,v in vars_values.items():
            if len(v) > 1:
                dyns.append(k)

        ndyn = len(dyns)
        nseries = len(series)
        if (nseries == 1 and ndyn > 0):
            """Only one serie: expand one dynamic variable as serie"""
            script,build,all_results = series[0]
            if ("var_serie" in script.config and script.config["var_serie"] in dyns):
                key=script.config["var_serie"]
            else:
                key=dyns[0]
            dyns.remove(key)
            ndyn-=1
            series=[]
            uuids=[]
            values = list(vars_values[key])
            values.sort()
            for value in values:
                newserie={}
                for run,results in all_results.items():
                    if (run.variables[key] == value):
                        newserie[run] = results
                series.append((script,build,newserie))
                if type(value) is tuple:
                    value=value[1]
                uuids.append(value)
                legend_title=self.var_name(key)
            nseries=len(series)

        else:
            key="uuid"
            legend_title=None

        ax = plt.gca()
        if (self.var_unit("result") == "BPS"):
            formatter = FuncFormatter(self.bits)
            ax.yaxis.set_major_formatter(formatter)

        reject_outliers = False

        #If more than 20 bars, do not print bar edges
        maxlen = max([len(serie[2]) for serie in series])
        if nseries * maxlen > 20:
            edgecolor = "none"
            interbar = 0.05
        else:
            edgecolor = None
            interbar = 0.1

        if ndyn == 0:
            """No dynamic variables : do a barplot X=uuid"""
            data=[]
            for a in [all_results for script,build,all_results in series]:
                v = list(a.values())[0]
                if v:
                    data.append(np.mean(v))
                else:
                    data.append(np.nan)

            i=0
            plt.bar(np.arange(len(uuids)) + interbar,data,label=uuids[i],color=graphcolor[i % len(graphcolor)],width=1-(2*interbar))
            plt.xticks(np.arange(len(uuids)) + 0.5,uuids, rotation='vertical' if (len(uuids) > 10) else 'horizontal')
        elif ndyn==1:
            """One dynamic variable used as X, series are uuid line plots"""
            key = dyns[0]

            xmin,xmax = (float('inf'),0)

            data=[]
            for all_results in [all_results for script,build,all_results in series]:
                x=[]
                y=[]
                e=[]
                for run in vars_all:
                    result = all_results.get(run,None)
                    x.append(run.print_variable(key))
                    if result:
                        if reject_outliers:
                            result = self.reject_outliers(np.asarray(result))
                        y.append(np.mean(result))
                        e.append(np.std(result))
                    else:
                        y.append(np.nan)
                        e.append(np.nan)
                order=np.argsort(x)
                data.append((np.array(x)[order],np.array(y)[order],np.array(e)[order]))

            for i,ax in enumerate(data):
                c = graphcolor[i % len(graphcolor)]
                plt.plot(ax[0],ax[1],label=uuids[i],color=c)
                plt.errorbar(ax[0],ax[1],yerr=ax[2], fmt='o',label=None,color=c)
                xmin = min(xmin , min(ax[0]))
                xmax = max(xmax , max(ax[0]))

            #Arrange the x limits
            var_lim = self.scriptconfig("var_lim",key,key)
            if var_lim and var_lim is not key:
                xmin,xmax = (float(x) for x in var_lim.split('-'))
            else:
                base = float(max(10,math.ceil((xmax - xmin) / 10)))
                if (xmin > 0):
                    xmin = int(math.floor(xmin / base)) * base
                if (xmax > 0):
                    xmax = int(math.ceil(xmax / base)) * base

            plt.gca().set_xlim(xmin,xmax)

            plt.legend(loc=self.config("legend_loc"), title=legend_title)
        else:
            """Barplot. X is all seen variables combination, series are UUID"""
            data=[]
            for all_results in [all_results for script,build,all_results in series]:
                y=[]
                e=[]
                for run in vars_all:
                    result = all_results.get(run,None)
                    if result:
                        if reject_outliers:
                            result = self.reject_outliers(np.asarray(result))
                        y.append(np.mean(result))
                        e.append(np.std(result))
                    else:
                        y.append(np.nan)
                        e.append(np.nan)
                data.append((y,e))
            width = (1-(2*interbar)) / len(uuids)
            ind = np.arange(len(vars_all))

            for i,serie in enumerate(data):
                plt.bar(interbar + ind + (i * width),serie[0],width,
                        label=str(uuids[i]),color=graphcolor[i % len(graphcolor)], yerr=serie[1],edgecolor=edgecolor)
            key = "Variables"
            ss = []
            for run in vars_all:
                s = []
                for k,v in run.variables.items():
                    if k in dyns:
                        s.append("%s = %s" % (self.var_name(k), str(v)))
                ss.append(','.join(s))

            plt.xticks(interbar + ind + width, ss, rotation='vertical' if (len(ss) > 5) else 'horizontal')
            if (ndyn > 0):
                plt.legend(loc=self.config("legend_loc"), title=legend_title)

        if ("result" in script.config['var_log']):
            plt.yscale('log')
        if (key in script.config['var_log']):
            plt.xscale('log')
        plt.xlabel(script.config.var_name(key))

        if ("result" in script.config["var_names"]):
            plt.ylabel(script.config["var_names"]["result"])

        if (ymin >= 0 and plt.ylim()[0] < 0):
            plt.ylim(0,plt.ylim()[1])

        if title:
            plt.title(title)
        plt.tight_layout()
        plt.savefig(filename)
        print("Graph of test written to %s" % filename)
        plt.clf()

    def reject_outliers(self, result):
        return next(self.scripts.__iter__()).reject_outliers(result)

