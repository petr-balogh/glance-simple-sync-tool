#!/usr/bin/python
import logging
import os
import argparse
import urlparse
import re
from glob import glob
from configobj import ConfigObj
from keystoneclient.v3.client import Client as KeystoneClient
from glanceclient.v2.client import Client as GlanceClient

TOOL_NAME = "glance-simple-sync-tool"
logger = logging.getLogger(TOOL_NAME)
CONFIG = 'glance-simple-sync.conf'
CONFIG_SECTIONS = ['base', 'glance_servers', 'images']

DEFAULT_KEYSTONE_V = 'v3'
DEFAULT_KEYSTONE_PORT = 5000
DEFAULT_GLANCE_V = 'v2'
DEFAULT_GLANCE_PORT = 9292
DEFAULT_TMP_DIR = '/tmp/%s' % TOOL_NAME

BACKUP_SUFFIX = 'sync_bak'


class GlanceWrapper(object):
    """
    Glance wrapper which create the auth token, and glance client object.
    Also it provides method like downlod_image, create_image, upload_image
    and other method which tool uses in sync process.
    """

    def __init__(self, name, **kwargs):
        """
        Initialization method for GlanceWrapper class.

        Args:
            name (str): Name of glance server from configuration

        Kwargs:
            url (str): url address of glance server
            port (str): port which server running, default: 9292
            version (str): version of glance API, default: v2
            user (str): username
            password (str): password
            tenant (str): tenant
            auth_url (str): url of keystone server, default: url of glance
            auth_port (str): port of keystone server, default: 5000
            auth_version (str) = version of keystone API, default: v3

        Returns:
            GlanceWrapper object
        """

        self.name = name
        self.url = kwargs.get('url')
        self.port = kwargs.get('port', DEFAULT_GLANCE_PORT)
        self.version = kwargs.get('version', DEFAULT_GLANCE_V)
        self.user = kwargs.get('username', 'admin')
        self.password = kwargs.get('password')
        self.tenant = kwargs.get('tenant', 'admin')
        self.auth_url = kwargs.get('auth_url', self.url)
        self.auth_port = kwargs.get('auth_port', DEFAULT_KEYSTONE_PORT)
        self.auth_version = kwargs.get('auth_version', DEFAULT_KEYSTONE_V)
        self._auth_token = None
        self._glance_obj = None

    def _get_url(self, url, port, version):
        _url = urlparse.urljoin(
            "%s:%s" % (url.rstrip('/'), port), version
        )
        return _url

    @property
    def token(self):
        """
        security token for auth.
        """

        if self._auth_token:
            return self._auth_token
        auth_url = self._get_url(
            self.auth_url, self.auth_port, self.auth_version
        )
        keystone = KeystoneClient(
            auth_url=auth_url, username=self.user, password=self.password,
            tenant=self.tenant
        )
        self._auth_token = keystone.session.get_token()
        return self._auth_token

    @property
    def glance_obj(self):
        """
        GlanceClient object
        """

        if self._glance_obj:
            return self._glance_obj
        url = self._get_url(self.url, self.port, self.version)
        return GlanceClient(endpoint=url, token=self.token)

    def get_images_dict(self, image_names=[], pattern=None):
        """
        Returns glance image dict of specified image_names or images which
        match pattern or both. If you dont's specify image_names neither
        pattern it returns all images on glance server.
        Returned dict looks like:
            {
                'image_name1': dict_of_image_data1,
                'image_name2': dict_of_image_data2,
            }

        Args:
            image_names (list): image names
            pattern (str): regexp

        Returns:
            dict of images which meet conditions
        """

        images = self.glance_obj.images.list()
        image_dict = {}
        for image in images:
            add_image = False
            for name in image_names:
                if name == image['name']:
                    add_image = True
                    break
            if not add_image and pattern and re.match(pattern, image['name']):
                add_image = True
            if not image_names and not pattern:
                add_image = True
            if add_image:
                image_dict[image['name']] = image
        return image_dict

    def download_image(self, image_id, path=DEFAULT_TMP_DIR):
        """
        Download image to specific path.

        Args:
            image_id (str): image id
            path (str): pathe where download image

        Returns:
            str path of downloaded image file
        """

        if not os.path.isdir(path):
            os.makedirs(path)
        file_path = os.path.join(path, image_id)
        if os.path.isfile(file_path):
            file_size = os.path.getsize(file_path)
            if self.get_image(image_id)['size'] != file_size:
                os.unlink(file_path)
            else:
                return file_path
        data = self.glance_obj.images.data(image_id)
        try:
            with open(file_path, 'w') as img_file:
                for data_chunk in data:
                    img_file.write(data_chunk)
        except IOError as ex:
            logger.error("Error when download image %s, Err: %s", image_id, ex)
        return file_path

    def create_image(self, **kwargs):
        """
        Create image from given params, you can pass dict whic describe image
        you got from glance.

        Kwargs:
            name (str): name of image
            container_format (str): container_format (e.g. bare)
            min_ram (int): min ram
            visibility (str): kind of visibility (private or public)
            min_disk (int): min disk
            disk_format (str): disk format (e.g. qcow2, raw)
            protected (bool): True if protected
        """

        return self.glance_obj.images.create(
            name=kwargs['name'], tags=kwargs.get('tags'),
            container_format=kwargs.get('container_format'),
            min_ram=kwargs.get('min_ram'),
            visibility=kwargs.get('visibility'),
            min_disk=kwargs.get('min_disk'),
            disk_format=kwargs.get('disk_format'),
            protected=kwargs.get('protected')
        )

    def upload_image(self, image_id, file_path):
        """
        Upload image file to glance server.

        Args:
            image_id (str): image id
            file_path (str): local path of image
        """

        with open(file_path, 'r') as image_file:
            self.glance_obj.images.upload(image_id, image_file)

    def rename_image(self, image_id, new_name):
        """
        Rename image.

        Args:
            image_id (str): image id
            new_name (str): new name of image
        """

        return self.glance_obj.images.update(image_id, name=new_name)

    def delete_image(self, image_id):
        """
        Delete image.

        Args:
            image_id (str): image id
        """

        self.glance_obj.images.delete(image_id)

    def get_image(self, image_id):
        """
        Get image information.

        Args:
            image_id (str): image id

        Returns:
            Dict of image information
        """

        return self.glance_obj.images.get(image_id)


def sync_images(
    master, slaves, image_names=[], pattern=None, path=DEFAULT_TMP_DIR
):
    """
    Method which sync images between master and slaves. If image_names
    neither pattern is not defined it sync all available images. If you define
    image_names it syncs all listed images, or if you define pattern, it sync
    all image which name match pattern. Both parameter are not mutiual
    exclusive, you can use both of them.

    Args:
        master (GlanceWrapper): master glance server
        slaves (list): slaves glance servers (GlanceWrapper)
        image_names (list): image name which sync
        pattern (string): regexp pattern for find images which sync
        path (str): path where you would like temporary store images
    """
    master_images = master.get_images_dict(image_names, pattern)
    for slave in slaves:
        slave_images = slave.get_images_dict(image_names, pattern)
        for image in master_images.itervalues():
            slave_image = slave_images.get(image['name'])
            if not slave_image:
                file_path = master.download_image(image['id'], path)
                created_image = slave.create_image(**image)
                slave.upload_image(created_image['id'], file_path)
                continue

            compare_key = 'checksum'
            if not image.get(compare_key) or not slave_image[compare_key]:
                compare_key = 'size'
            if image[compare_key] != slave_image[compare_key]:
                file_path = master.download_image(image['id'], path)
                backup_name = '%s_%s' % (image['name'], BACKUP_SUFFIX)
                try:
                    slave.rename_image(slave_image['id'], backup_name)
                    created_image = slave.create_image(**image)
                    slave.upload_image(created_image['id'], file_path)
                    slave.delete_image(slave_image['id'])
                except Exception as ex:
                    logger.error(
                        'Error when creating or uploading image %s, err: %s',
                        image['name'], ex
                    )
                    if image['name'] in slave.get_images_dict():
                        slave.delete_image(image['name'])
                        raise


def clean_tmp_dir(tmp_dir=DEFAULT_TMP_DIR):
    """
    Cleaning tmp dir

    Args:
        tmp_dir (str): tmp dir path
    """
    logger.info("Cleaning TMP dir %s", tmp_dir)
    for file_ in glob(os.path.join(tmp_dir, '*')):
        logger.debug('Removing file: %s', file_)
        os.unlink(file_)


def get_parser():
    parser = argparse.ArgumentParser(description="Glance siple sync tool")
    default_config_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), CONFIG
    )
    parser.add_argument(
        '--config', help='Config file path', default=default_config_path
    )
    parser.add_argument(
        '--tmpdir', '-t', help=(
            'Temprorary dir for storing downloaded images. Default is %s'
            % DEFAULT_TMP_DIR
        )
    )
    parser.add_argument(
        '--pattern', '-p', help='Image pattern which sync', nargs='?'
    )
    parser.add_argument(
        '--images', '-i', help='list of images separated with space',
        nargs='+'
    )
    parser.add_argument(
        '--master', '-m',
        help='Name of master glance server from config section glance_servers'
    )
    parser.add_argument(
        '--slaves', '-s', nargs='+',
        help='Name of glance servers separated with space, where sync images '
        'from master, slaves have to be defined in config under glance_servers'
        ' section'
    )
    parser.add_argument('--verbose', '-v', action='store_true', help="verbose")
    parser.add_argument(
        '--clean', '-c', action='store_true',
        help='Clean TMP dir after syncing images'
    )
    return parser


def config_tool():
    parser = get_parser()
    args_ = parser.parse_args()
    logging_level = logging.DEBUG if args_.verbose else logging.INFO
    logging.basicConfig(level=logging_level)
    if os.path.isfile(args_.config):
        config = ConfigObj(args_.config)
    else:
        logger.error("Didn't find config file: %s", args_.config)
        parser.print_help()
        exit(1)
    try:
        config['base']['master'] = args_.master or config['base']['master']
        config['base']['slaves'] = args_.slaves or config['base']['slaves']
        config['base']['tmpdir'] = (
            args_.tmpdir or config['base'].get('tmpdir') or DEFAULT_TMP_DIR
        )
        config['base']['clean'] = args_.clean or config['base'].get('clean')
        config['images']['sync_list'] = (
            args_.images or config['images'].get('sync_list')
        )
        config['images']['pattern'] = (
            args_.pattern or config['images'].get('pattern')
        )
    except KeyError as ex:
        logger.error(
            "Failed during read configuration, probably you missed something "
            "define in config or pass it as argument. Err: %s", ex
        )
        parser.print_help()
        exit(1)
    return config


if __name__ == '__main__':
    conf = config_tool()
    glance_servers = {}
    for srv_name, srv_conf in conf.get('glance_servers', {}).iteritems():
        glance_servers[srv_name] = GlanceWrapper(srv_name, **srv_conf)
    try:
        master = glance_servers[conf['base'].get('master')]
    except KeyError:
        logger.error("Couldn't find master in config file")
        raise
    try:
        slaves = [
            glance_servers[slave] for slave in conf['base'].as_list('slaves')
        ]
    except KeyError:
        logger.error("Couldn't find slaves in configuration!")
        raise
    sync_images(
        master, slaves, conf['images'].as_list('sync_list'),
        conf['images'].get('pattern'), conf['base'].get('tmpdir')
    )
    if conf['base'].get('clean'):
        clean_tmp_dir(conf['base'].get('tmpdir'))
