from krita import *
import json
import os
import logging
import threading
import socket
from krita_stable_diffusion.interface.interfaces.panel import KritaDockWidget

class Controller(QObject):
    krita_instance = None
    config = None
    stop_socket_connection = None

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

    def run(self):
        """
        Starts a new thread with a client that has a connection to stablediffusion_responsed
        :return: None
        """
        # connect to stablediffusion_responsed socket in a separate thread
        self.thread = threading.Thread(target=self.connect_to_stablediffusion_responsed, daemon=False)
        self.thread.start()

    def connect_to_stablediffusion_responsed(self):
        """
        Do not call this function directly, use run() instead
        :return: None
        """
        self.SOCK = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.SOCK.connect(("localhost", 50007))
        self.listen_for_responses()

    def disconnect_from_stablediffusion_responsed(self):
        """
        Stops the stablediffusion_responsed socket connection
        :return: None
        """
        self.SOCK.close()

    def reconnect_to_stablediffusion_responsed(self):
        """
        Reconnects to stablediffusion_responsed
        :return: None
        """
        self.disconnect_from_stablediffusion_responsed()
        self.thread.join(timeout=0)
        self.run()

    def listen_for_responses(self):
        print("Starting stablediffusion_responsed listener")
        # open a connection to localhost:50007
        check_stream = True
        while check_stream:
            image_paths = []
            try:
                image_paths = json.loads(self.SOCK.recv(1024))
            except Exception as e:
                print(e)
                check_stream = False
            if len(image_paths) > 0:
                self.insert_images(image_paths)
                self.active_document.refreshProjection()
                self.delete_generated_images(image_paths)

    def insert_images(self, image_paths):
        """
        Inserts images into the active document
        :param image_paths:
        :return:
        """
        layer_name_prefix = "SD_txt2img:"
        for image_data in image_paths:
            # seed = image_data.__contains__("seed") or ""
            # image_path = image_data["image"]
            image_path = image_data
            seed = ""
            self.add_image(f"{layer_name_prefix}:{seed}:{image_path}", image_path)

    def create_layer(self, name, visible=True, type="paintLayer"):
        """
        Creates a new layer in the active document
        :param name:
        :param type:
        :return: a reference to the new layer
        """
        logging.info(f"creating layer")
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
        logging.info(f"converting image to byte array")
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
        logging.info(f"adding image: {path}")
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.init_settings(**kwargs)
        self.thread = None
        self.create_stable_diffusion_panel()
        Application.__setattr__("restart_stablediffusiond", self.reconnect_to_stablediffusion_responsed)

        self.run()


controller = Controller()