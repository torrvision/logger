import copy
import git
import time
import json
import numpy as np
import sys

from builtins import dict
from collections import defaultdict

from .metrics import TimeMetric_, AvgMetric_, SumMetric_, ParentWrapper_,\
    SimpleMetric_

# pickle for python 2 / 3
if sys.version_info[0] == 2:
    import cPickle as pickle
else:
    import pickle

# optional visdom
try:
    import visdom
except ImportError:
    visdom = None


class Experiment(object):

    def __init__(self, name, log_git_hash=True,
                 use_visdom=False, visdom_opts={}):
        """ Create an experiment with the following parameters:
        - log_git_hash (bool): retrieve current commit hash to log code status
        - use_visdom (bool): monitor metrics logged on visdom
        - visdom_opts (dict): options for visdom
        """

        super(Experiment, self).__init__()

        self.name = name
        self.date_and_time = time.strftime('%d-%m-%Y--%H-%M-%S')

        self.logged = defaultdict(dict)
        self.metrics = defaultdict(dict)

        self.config = dict()
        self.use_visdom = use_visdom

        if self.use_visdom:
            assert visdom is not None, "visdom could not be imported"
            # visdom env is given by Experiment name unless specified
            if 'env' not in list(visdom_opts.keys()):
                visdom_opts['env'] = name
            self.viz = visdom.Visdom(**visdom_opts)
            self.viz_dict = dict()

        if log_git_hash:
            self.log_git_hash()

    def NewMetric_(self, name, tag, Metric_):

        assert name not in list(self.metrics[tag].keys()), \
            "metric with tag {} and name {} already exists".format(tag, name)

        metric = Metric_(name, tag)
        self.metrics[tag][name] = metric

        return metric

    def AvgMetric(self, name, tag="default"):
        return self.NewMetric_(name, tag, AvgMetric_)

    def SimpleMetric(self, name, tag="default"):
        return self.NewMetric_(name, tag, SimpleMetric_)

    def TimeMetric(self, name, tag="default"):
        return self.NewMetric_(name, tag, TimeMetric_)

    def SumMetric(self, name, tag="default"):
        return self.NewMetric_(name, tag, SumMetric_)

    def ParentWrapper(self, name, tag="default", children=()):

        for child in children:

            # continue if child tag is same as parent's
            if child.tag == tag:
                continue

            # else remove child from previous tagging
            self.metrics[child.tag].pop(child.name)

            # update child's tag
            child.tag = tag

            # update tagging
            self.metrics[child.tag][child.name] = child

        metric = ParentWrapper_(children)
        self.metrics[tag][name] = metric

        return metric

    def log_git_hash(self):

        try:
            repo = git.Repo(search_parent_directories=True)
            self.log_config({'git_hash': repo.head.object.hexsha})
        except:
            print("I tried to find a git repository in current "
                  "and parent directories but did not find any.")

    def log_config(self, config_dict):
        self.config.update(config_dict)

    def log_with_tag(self, tag):

        # gather all metrics with given tag except Parents
        # (to avoid logging twice the information)
        metrics = (m for m in self.metrics[tag].values()
                   if not isinstance(m, ParentWrapper_))

        # log all metrics
        for metric in metrics:
            self.log_metric(metric)

    def log_metric(self, metric):

        # log only child metrics
        if isinstance(metric, ParentWrapper_):
            for child in metric.children.values():
                self.log_metric(child)
            return

        tag, name = metric.tag, metric.name
        key = "{}_{}".format(name, tag)
        self.logged[key][metric.timer.get()] = metric.get()

        if self.use_visdom and not isinstance(metric, TimeMetric_):
            try:
                x = np.array([metric.timer.get()])
                y = np.array([metric.get()])
                if name not in list(self.viz_dict.keys()):
                    self.viz_dict[name] = \
                        self.viz.line(Y=y, X=x,
                                      opts={'legend': [tag],
                                            'title': name,
                                            'xlabel': 'Time (s)'})
                else:
                    self.viz.updateTrace(Y=y, X=x,
                                         name=tag,
                                         win=self.viz_dict[name],
                                         append=True)
            except:
                # if an error occurs, warn user and give up monitoring
                # (useful if connection is lost for instance)
                print('I could not send my data to Visdom :(\n'
                      'Giving up monitoring.')
                self.use_visdom = False

    def get_metric(self, name, tag="default"):

        assert tag in list(self.metrics.keys()) and name in list(self.metrics[tag].keys())

        return self.metrics[tag][name]

    def to_pickle(self, filename):

        var_dict = copy.copy(vars(self))
        var_dict.pop('metrics')
        for key in ('viz', 'viz_dict'):
            if key in list(var_dict.keys()):
                var_dict.pop(key)
        with open(filename, 'wb') as f:
            pickle.dump(var_dict, f)

    def to_json(self, filename):

        var_dict = copy.copy(vars(self))
        var_dict.pop('metrics')
        for key in ('viz', 'viz_dict'):
            if key in list(var_dict.keys()):
                var_dict.pop(key)
        with open(filename, 'w') as f:
            json.dump(var_dict, f)
