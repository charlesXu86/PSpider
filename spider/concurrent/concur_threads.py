# _*_ coding: utf-8 _*_

"""
concur_threads.py by xianhu
"""

import copy
import queue
import logging
import threading
from .concur_abase import TPEnum, BasePool
from .concur_threads_insts import FetchThread, ParseThread, SaveThread, MonitorThread


class ThreadPool(BasePool):
    """
    class of ThreadPool, as the subclass of BasePool
    """

    def __init__(self, fetcher, parser, saver, url_filter=None, monitor_sleep_time=5):
        """
        constructor
        """
        BasePool.__init__(self, fetcher, parser, saver, url_filter=url_filter)

        self._fetch_queue = queue.PriorityQueue()    # (priority, url, keys, deep, repeat)
        self._parse_queue = queue.PriorityQueue()    # (priority, url, keys, deep, content)
        self._save_queue = queue.Queue()             # (url, keys, item), item can be anything

        self._lock = threading.Lock()                # the lock which self._number_dict needs

        # set monitor thread
        self._monitor_stop = False
        self._monitor = MonitorThread("monitor", self, sleep_time=monitor_sleep_time)
        self._monitor.setDaemon(True)
        self._monitor.start()
        return

    def start_work_and_wait_done(self, fetcher_num=10, is_over=True):
        """
        start this pool, and wait for finishing
        :param fetcher_num: not useful if self._inst_fetcher is a list or tuple
        :param is_over: stop monitor thread or not, default True
        """
        logging.warning("%s start: fetcher_num=%s, is_over=%s", self.__class__.__name__, fetcher_num, is_over)

        if isinstance(self._inst_fetcher, (list, tuple)):
            fetcher_list = [FetchThread("fetcher-%d" % (i+1), fetcher, self) for (i, fetcher) in enumerate(self._inst_fetcher)]
        else:
            fetcher_list = [FetchThread("fetcher-%d" % (i+1), copy.deepcopy(self._inst_fetcher), self) for i in range(fetcher_num)]
        parser_saver_list = [ParseThread("parser", self._inst_parser, self), SaveThread("saver", self._inst_saver, self)]

        # 1-----
        for thread in fetcher_list:
            thread.setDaemon(True)
            thread.start()

        # 1-----
        for thread in parser_saver_list:
            thread.setDaemon(True)
            thread.start()

        # 2-----
        for thread in fetcher_list:
            if thread.is_alive():
                thread.join()

        # clear the variables if all fetcher stoped
        while self.get_number_dict(TPEnum.URL_NOT_FETCH) > 0:
            self.get_a_task(TPEnum.URL_FETCH)
            self.finish_a_task(TPEnum.URL_FETCH)

        # 2-----
        for thread in parser_saver_list:
            if thread.is_alive():
                thread.join()

        # 3-----
        if is_over and self._monitor.is_alive():
            self._monitor_stop = True
            self._monitor.join()

        logging.warning("%s end: fetcher_num=%s, is_over=%s", self.__class__.__name__, fetcher_num, is_over)
        return

    def update_number_dict(self, key, value):
        """
        update the value of self._number_dict based on key
        """
        self._lock.acquire()
        self._number_dict[key] += value
        self._lock.release()
        return

    def get_monitor_stop_flag(self):
        """
        get the monitor stop flag of this pool
        """
        return self._monitor_stop

    # ================================================================================================================================
    def add_a_task(self, task_name, task_content):
        """
        add a task based on task_name
        """
        if task_name == TPEnum.URL_FETCH and ((task_content[-1] > 0) or (not self._url_filter) or self._url_filter.check_and_add(task_content[1])):
            self._fetch_queue.put_nowait(task_content)
            self.update_number_dict(TPEnum.URL_NOT_FETCH, +1)
        elif task_name == TPEnum.HTM_PARSE:
            self._parse_queue.put_nowait(task_content)
            self.update_number_dict(TPEnum.HTM_NOT_PARSE, +1)
        elif task_name == TPEnum.ITEM_SAVE:
            self._save_queue.put_nowait(task_content)
            self.update_number_dict(TPEnum.ITEM_NOT_SAVE, +1)
        return

    def get_a_task(self, task_name):
        """
        get a task based on task_name, if queue is empty, raise queue.Empty
        """
        task_content = None
        if task_name == TPEnum.URL_FETCH:
            task_content = self._fetch_queue.get(block=True, timeout=5)
            self.update_number_dict(TPEnum.URL_NOT_FETCH, -1)
        elif task_name == TPEnum.HTM_PARSE:
            task_content = self._parse_queue.get(block=True, timeout=5)
            self.update_number_dict(TPEnum.HTM_NOT_PARSE, -1)
        elif task_name == TPEnum.ITEM_SAVE:
            task_content = self._save_queue.get(block=True, timeout=5)
            self.update_number_dict(TPEnum.ITEM_NOT_SAVE, -1)
        self.update_number_dict(TPEnum.TASKS_RUNNING, +1)
        return task_content

    def finish_a_task(self, task_name):
        """
        finish a task based on task_name, call queue.task_done()
        """
        if task_name == TPEnum.URL_FETCH:
            self._fetch_queue.task_done()
        elif task_name == TPEnum.HTM_PARSE:
            self._parse_queue.task_done()
        elif task_name == TPEnum.ITEM_SAVE:
            self._save_queue.task_done()
        self.update_number_dict(TPEnum.TASKS_RUNNING, -1)
        return
    # ================================================================================================================================
