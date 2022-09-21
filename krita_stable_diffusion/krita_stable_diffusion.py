import json
import sys
import time

from krita import *
import threading
import os
import krita_stable_diffusion.logger as log

#from krita_stable_diffusion.connect import StablediffusionresponsedConnection
from krita_stable_diffusion.connect import StableDiffusionRequestQueueWorker, SimpleEnqueueSocketClient
from krita_stable_diffusion.interface.interfaces.panel import KritaDockWidget

class Controller(QObject):
    krita_instance = None
    config = None
    stop_socket_connection = None
    log = []
    threads = []
    first_run = True
    name = "Controller"


    def start_thread(self, target, daemon=False, name=None):
        t = threading.Thread(target=target, daemon=daemon)
        if name:
            t.setName(name)
        t.start()
        self.threads.append(t)
        return t

    def stop(self):
        print("Stopping client")
        self.client.quit()
        for n in range(len(self.threads)):
            thread = self.threads[n]
            print(f"{n+1} of {len(self.threads)} Stopping thread {thread.getName()} from {self.name}...")
            try:
                thread.join()
            except:
                print("Failed to join thread")
            print(f"Stopped thread {thread.getName()}...")
        print(f"All threads in {self.name} stopped")

    @property
    def krita(self):
        if not self.krita_instance:
            self.krita_instance = Krita.instance()
        return self.krita_instance

    @property
    def selection(self):
        return self.active_document.selection()

    def x(self):
        return 0 if self.selection is None else self.selection.x()

    def y(self):
        return 0 if self.selection is None else self.selection.y()

    @property
    def active_document(self):
        return self.krita.activeDocument()

    @property
    def root_node(self):
        return self.active_document.rootNode()

    def width(self):
        return self.active_document.width() if self.selection is None else self.selection.width()

    def height(self):
        return self.active_document.height() if self.selection is None else self.selection.height()

    @property
    def img2img_base_size(self ):
        return self.config.value('img2img_base_size', int)

    @img2img_base_size.setter
    def img2img_base_size(self, value):
        self.config.setValue('img2img_base_size', value)

    @property
    def img2img_max_size(self):
        return self.config.value('img2img_max_size', int)

    @img2img_max_size.setter
    def img2img_max_size(self, value):
        self.config.setValue('img2img_max_size', value)

    @property
    def txt2img_seed(self):
        return self.config.value('txt2img_seed', int)

    @txt2img_seed.setter
    def txt2img_seed(self, value):
        self.config.setValue('txt2img_seed', value)

    @property
    def workaround_timeout(self):
        self.config.value('workaround_timeout', bool)

    @workaround_timeout.setter
    def workaround_timeout(self, value):
        self.config.setValue('workaround_timeout', value)

    @property
    def img2img_seed(self):
        self.config.value('img2img_seed', bool)

    @img2img_seed.setter
    def img2img_seed(self, value):
        self.config.setValue('img2img_seed', value)

    def stablediffusion_responsed_callback(self, response):
        """
        Handles response from Stable Diffusion service
        :param response:
        :return:
        """
        self.insert_images(response)
        self.active_document.refreshProjection()
        self.delete_generated_images(response)

    def insert_images(self, image_paths):
        """
        Inserts images into the active document
        :param image_paths:
        :return:
        """
        layer_name_prefix = "SD_txt2img:"
        image_paths = json.loads(image_paths)
        for image_data in image_paths:
            seed = image_data.__contains__("seed") or ""
            image_path = image_data["file_name"]
            self.add_image(f"{layer_name_prefix}:{seed}:{image_path}", image_path)

    def create_layer(self, name, visible=True, type="paintLayer"):
        """
        Creates a new layer in the active document
        :param name:
        :param type:
        :return: a reference to the new layer
        """
        log.info(f"creating layer")
        document = self.active_document.createNode(name, type)
        self.root_node.addChildNode(document, None)
        document.setVisible(visible)
        return document

    def byte_array(self, image):
        """
        Convert QImage to QByteArray
        :param image:
        :return: QByteArray
        """
        log.info(f"converting image to byte array")
        bits = image.bits()
        bits.setsize(image.byteCount())
        return QByteArray(bits.asstring())

    def add_image(self, layer_name, path, visible=True):
        """
        Loads image from path and adds it to the active document
        :param layer_name:
        :param path:
        :param visible:
        :return:
        """
        log.info(f"adding image: {path}")
        image = QImage()
        image.load(path, "PNG")
        layer = self.create_layer(layer_name, visible=visible)
        layer.setPixelData(self.byte_array(image), self.x(), self.y(), self.width(), self.height())

    def delete_generated_images(self, files):
        for file in files:
            os.remove(file)

    def init_settings(self, **kwargs):
        # create settings objects for various tabs and also main settings
        Application.__setattr__("krita_stable_diffusion_config", QSettings(
            QSettings.IniFormat,
            QSettings.UserScope,
            "krita",
            "krita_stable_diffusion"
        ))
        self.config = Application.krita_stable_diffusion_config

        # initialize default settings
        for k, v in kwargs.get("defaults", {}).items():
            if not self.config.contains(k):
                self.config.setValue(k, v)

    def create_stable_diffusion_panel(self):
        Application.addDockWidgetFactory(
            DockWidgetFactory(
                "krita_stable_diffusion",
                DockWidgetFactoryBase.DockRight,
                KritaDockWidget
            )
        )

    def stablediffusion_response_callback(self, msg):
        print("STABLE DIFFUSION RESPONSE CALLBACK", msg)
        self.insert_images(msg)

    def kritastablediffusion_service_start(self):
        """
        Launches kritastablediffusion service
        :return:
        """
        here = os.path.dirname(os.path.realpath(__file__))
        # get process id for the current process
        pid = os.getpid()
        #os.system(f"{here}/dist/kritastablediffusion/kritastablediffusion --pid {pid}")
        os.system(f"/home/joe/miniconda3/envs/kritastablediffusion/bin/python {here}/kritastablediffusion.py --pid {pid} &")

    def request_prompt(self, message):
        """
        Sends prompt request to stable diffusion
        :param message:
        :return:
        """
        self.client.message = json.dumps(message).encode("ascii")

    def handle_sd_response(self, response):
        log.info("Handle stable diffusion response")
        # TODO handle image insertion here

    def try_quit(self):
        try:
            if hasattr(Application, "activated") and Application.activeWindow() is None:
                self.stop()
                return True
            elif Application.activeWindow():
                Application.__setattr__("activated", True)
        except Exception as e:
            print("application dead", e)
            pass
        return False

    def watch_connection(self):
        while True:
            if self.try_quit():
                self.quit_event.set()
                break
            time.sleep(1)

    def __init__(self, *args, **kwargs):
        self.client = None
        super().__init__(*args, **kwargs)
        self.init_settings(**kwargs)
        self.create_stable_diffusion_panel()
        Application.__setattr__("stablediffusion", self)
        # on Application quit, close the server
        Krita.instance().eventFilter = self.eventFilter
        self.quit_event = threading.Event()
        self.quit_event.clear()
        self.client = SimpleEnqueueSocketClient(
            port=50006,
            handle_response=self.stablediffusion_response_callback
        )
        self.start_thread(
            target=self.kritastablediffusion_service_start,
            name="kritastablediffusion"
        )
        self.start_thread(
            target=self.watch_connection,
            name="watch_connection"
        )


controller = Controller()
