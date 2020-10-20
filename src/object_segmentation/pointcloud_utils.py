import numpy as np
import cv2
import rospy
from sensor_msgs.msg import CameraInfo
import image_geometry
import struct
from datetime import datetime
from sensor_msgs.msg import PointField
from std_msgs.msg import Header
from sensor_msgs import point_cloud2
import tf2_ros
from geometry_msgs.msg import Point, Pose, TransformStamped, Quaternion
from tf.transformations import quaternion_from_euler


class CameraModel:
    def __init__(self, topic):
        self.camera_model = None
        self.camera_info_sub = rospy.Subscriber(topic, CameraInfo, self.camera_info_callback)

    def camera_info_callback(self, camera_info_msg):
        if self.camera_model is not None:
            return
        self.camera_model = image_geometry.PinholeCameraModel()
        self.camera_model.fromCameraInfo(camera_info_msg)


def decompress_img(compressed_msg):
    np_arr = np.fromstring(compressed_msg.data, np.uint8)
    image_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    return image_rgb


def decompress_depth(compressed_msg):
    np_arr = np.fromstring(compressed_msg.data, np.uint16)
    image_depth = cv2.imdecode(np_arr, cv2.IMREAD_ANYDEPTH)
    return image_depth


def pts_to_ptmsg(pts, frame_id):
    fields = [PointField('x', 0, PointField.FLOAT32, 1),
              PointField('y', 4, PointField.FLOAT32, 1),
              PointField('z', 8, PointField.FLOAT32, 1),
              # PointField('rgb', 12, PointField.UINT32, 1),
              PointField('rgba', 12, PointField.UINT32, 1),
              ]
    header = Header()
    header.frame_id = frame_id
    pt_msg = point_cloud2.create_cloud(header, fields, pts)
    return pt_msg


def convert_depth_img_to_pointcloud(depth_image, img, camera_model, max_depth=np.inf):
    center_x = camera_model.cx()
    center_y = camera_model.cy()

    unit_scaling = 0.001  # TODO: Mimic DepthTraits and check type: If float, no scaling
    # https://github.com/ros-perception/image_pipeline/blob/melodic/depth_image_proc/src/nodelets/point_cloud_xyzrgb.cpp

    constant_x = unit_scaling / camera_model.fx()
    constant_y = unit_scaling / camera_model.fy()

    w, h = depth_image.shape

    valid_inds = np.nonzero(np.logical_and(depth_image > 0, depth_image < max_depth / unit_scaling))

    pts = []
    for u, v in zip(valid_inds[0], valid_inds[1]):
        depth = depth_image[u, v]
        if depth == 0.0:
            continue
        x = (v - center_x) * depth * constant_x
        y = (u - center_y) * depth * constant_y
        z = unit_scaling * depth

        r, g, b = img[u, v]
        a = 255
        rgb = struct.unpack('I', struct.pack('BBBB', b, g, r, a))[0]

        pts.append([x, y, z, rgb])

    return pts


def convert_masked_depth_img_to_pointcloud(depth_img, img, mask, camera_model, categories):
    center_x = camera_model.cx()
    center_y = camera_model.cy()

    unit_scaling = 0.001  # TODO: Mimic DepthTraits and check type: If float, no scaling
    # https://github.com/ros-perception/image_pipeline/blob/melodic/depth_image_proc/src/nodelets/point_cloud_xyzrgb.cpp

    constant_x = unit_scaling / camera_model.fx()
    constant_y = unit_scaling / camera_model.fy()

    # matched_categories = [6, 13, 21, 14]

    inds = (np.array([], np.int8), np.array([], np.int8))
    for cat in categories:
        cat_inds = np.nonzero(mask[:, :, 0] == cat)
        inds = (np.append(inds[0], cat_inds[0]), np.append(inds[1], cat_inds[1]))

    if False:
        import matplotlib.pyplot as plt
        plt.imshow(mask)
        plt.show()

    pts = []
    for u, v in zip(inds[0], inds[1]):
        depth = depth_img[u, v]
        if depth == 0.0:
            continue
        x = (v - center_x) * depth * constant_x
        y = (u - center_y) * depth * constant_y
        z = unit_scaling * depth

        if z > 1.5:
            continue

        r, g, b = img[u, v]
        a = 255
        rgb = struct.unpack('I', struct.pack('BBBB', b, g, r, a))[0]

        pts.append([x, y, z, rgb])

    return pts
