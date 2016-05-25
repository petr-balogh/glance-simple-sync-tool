# glance-simple-sync-tool

glance-simple-sync-tool
-----------------
Is tool for syncing images between two or more glance servers when one is MASTER and others are slaves.

Configuration of glance servers and cofnigurations for tool are store in config file which is default glance-simple-sync.conf

usage of script:
	./glance_sync.py --help
and you will see all arguments which you can use.

If you don't specify images for sync it sync all images from master.
You can specify images, patter or both of them to match which images sync.

Basic configuration looks like:

	[base]
	  master = master-name
	  slaves = slave-name1
	  # tmpdir = /tmp/tmpdirname
      # clean = True # if clean tmpdir after syncing images

	[glance_servers]
      [[master-name]]
        keystone_v = v3 # optional parameter, it is default value in code
        glance_v = v2 # optional parameter, it is default value in code
        username = admin
        password = change_me
        tenant = admin
        url = http://master.url.com

      [[slave-name1]]
        username = admin
        password = change_me
        tenant = admin
        url = http://localhost

      [[slave-name2]]
        username = admin
        password = change_me
        tenant = admin
        url = http://another.url.com

	  [images]
	    sync_list = test1_image,test2_image # optional, you can also specify it as --images argument of script. If you dont specify it, it will sync all images from master.
        # pattern = .* # optional, you can also specify it as --pattern argument of script


You can set cron to run this script repeatedly
*/20 * * * * /path/to/glance-sync.py # run it every 20 min
