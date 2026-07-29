# =============================================================================
# NeuSpeech Institute, NeuGaze Project
# Copyright (c) 2024 Yiqian Yang
#
# This code is part of the NeuGaze project developed at NeuSpeech Institute.
# Author: Yiqian Yang
#
# This work is licensed under the Creative Commons Attribution-NonCommercial 4.0 
# International License. To view a copy of this license, visit:
# http://creativecommons.org/licenses/by-nc/4.0/
# =============================================================================

from collections.abc import Mapping
from numbers import Real
import copy
import os
import pathlib
import queue
import sys
from typing import Union
import cv2
import numpy as np
import math
import torch
import torch.nn as nn
import pickle
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import time
import matplotlib.pyplot as plt
import json
from sklearn.linear_model import Ridge, Lasso, MultiTaskLassoCV, Lars, SGDRegressor, ElasticNet
from sklearn.neural_network import MLPRegressor
from sklearn.multioutput import MultiOutputRegressor
from .vis import render
from sklearn.ensemble import RandomForestRegressor
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.svm import SVR
from .results import GazeResultContainer, IntegratedGazeResultContainer,AllResultContainer
from .vis import popout_fading_window
import datetime
import jsonlines
from .utils import rotation_matrix_to_angles, StateRecordDict, combine_dicts
from .utils import (generate_calibration_points, generate_random_calibration_points, GazeKalmanFilter,
                    plot_points, crop_center_rectangle, getArch, read_jsonlines)
from .expression_evaluator import ExpressionEvaluator
from . import desktop
from .camera import camera_config_from_mapping, open_camera
import threading
import tkinter as tk
from .keyboard_utils import Action, OpType
from .robot_actions import (
    RobotAction,
    emit_robot_action,
    emit_robot_action_cancelled,
    resolve_robot_action,
    validate_robot_action_config,
)
import ncnn
import torch.nn as nn
import torchvision.transforms as transforms
import threading
import jsonlines
import json
import math
import threading
import time
import os
import pathlib
from typing import Union
from datetime import datetime
    



mediapipe_desired_points = [
    70, 63, 105, 66, 107,  # 左边眉毛上面
    46, 53, 52, 65, 55,  # 左边眉毛下面
    33, 246, 161, 160, 159, 158, 157, 173, 133, 155, 154, 153, 145, 144, 163, 7,  # 左边眼睛一周
    468, 469, 470, 471, 472,  # 左边虹膜

    336, 296, 334, 293, 300,  # 右边眉毛上面
    285, 295, 282, 283, 276,  # 右边眉毛下面
    362, 398, 384, 385, 386, 387, 388, 466, 263, 249, 390, 373, 374, 380, 381, 382,  # 右边眼睛一周
    473, 474, 475, 476, 477,  # 右边虹膜
    0, 1, 4, 5, 6, 8, 9, 10,
    234, 227, 454, 447, 127, 356,
]


def get_screen_resolution():
    screen = cv2.getWindowImageRect('Gaze Tracking')
    return screen[2], screen[3]


def get_box_from_points(points_xy):
    x = points_xy[:, 0]
    y = points_xy[:, 1]
    return [min(x), max(x), min(y), max(y)]


def get_some_landmark_from_result(result, image_width=None, image_height=None):
    faces_landmarks = result.face_landmarks
    faces_landmarks_numpy = []
    for face_landmarks in faces_landmarks:
        face_landmarks_numpy = []
        for i, landmark in enumerate(face_landmarks):
            if i in mediapipe_desired_points:
                x = landmark.x
                y = landmark.y
                face_landmarks_numpy.append([x, y])
        faces_landmarks_numpy.append(face_landmarks_numpy)
    faces_landmarks_numpy = np.array(faces_landmarks_numpy)
    return faces_landmarks_numpy


def get_all_landmark_from_result(result, image_width=None, image_height=None):
    faces_landmarks = result.face_landmarks
    faces_landmarks_numpy = []
    t00 = time.time()
    for face_landmarks in faces_landmarks:
        face_landmarks_numpy = []
        t0 = time.time()
        for i, landmark in enumerate(face_landmarks):
            x = landmark.x
            y = landmark.y
            z = landmark.z
            face_landmarks_numpy.append([x, y, z])
        t1 = time.time()
        # print(f'faces_landmarks:{t1-t0}')
        faces_landmarks_numpy.append(face_landmarks_numpy)

    t2 = time.time()
    faces_landmarks_numpy = np.array(faces_landmarks_numpy)
    t3 = time.time()
    # print(f'faces_landmarks_numpy:{t3-t2}')
    # print(f'faces_landmarks all:{t3-t00}')
    return faces_landmarks_numpy


def resize_and_place_image(small_img, big_img, scale_fraction=1 / 8):
    imgA = small_img
    imgB = big_img

    # 获取图像A和B的尺寸
    height_A, width_A = imgA.shape[:2]
    height_B, width_B = imgB.shape[:2]

    # 计算图像A缩放后的尺寸（B图像宽度的scale_fraction）
    new_width_A = int(width_B * scale_fraction)
    new_height_A = int((new_width_A / width_A) * height_A)

    # 缩放图像A
    resized_imgA = cv2.resize(imgA, (new_width_A, new_height_A), interpolation=cv2.INTER_AREA)

    # 将缩放后的图像A放置在图像B的左上方
    y1, y2 = 0, new_height_A
    x1, x2 = 0, new_width_A
    imgB[y1:y2, x1:x2] = resized_imgA
    return imgB


def prep_input_numpy(img: np.ndarray, device: str):
    """Preparing a Numpy Array as input to L2CS-Net."""

    if len(img.shape) == 4:
        imgs = []
        for im in img:
            imgs.append(transformations(im))
        img = torch.stack(imgs)
    else:
        img = transformations(img)

    img = img.to(device)

    if len(img.shape) == 3:
        img = img.unsqueeze(0)

    return img


import torchvision
from torchvision import transforms

transformations = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize(224),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    )
])




class IntegratedRegressionMediaPipeline:
    def __init__(
            self,
            weights: pathlib.Path,
            regression_model_type: str = 'ridge',
            regression_model_path: str = None,
            arch: str = 'ResNet50',
            device: str = torch.device('cuda'),
            cam_id: int = 0,
            camera_backend=None,
            camera_width=None,
            camera_height=None,
            camera_fps=None,
            num_points=20,
            screen_size=[None,None],
            every_point_has_n_images=15,
            images_freq=5,
            each_point_wait_time=1000,
            edge=0.1,
            radius=20,
            func='sequence',
            window_name='track',
            render_in_eval=False,
            start_with_calibration=False,
            is_calibrating=False,
            pred_point_color=(0, 0, 255),
            true_point_color=(0, 255, 0),
            gaze_bias=(0, 0),
            kalman_filter_std_measurement=0.2,
            dt: float = 0.04,
            Q_coef: float = 0.03,
            eye_blink_threshold = 0.5,
            use_accumulated_training: bool = True,  # 新增：是否使用累积训练
            max_accumulated_datasets: int = 10,     # 新增：最大累积数据集数量
            ):
        self.mediapipe_results_in_numpy = None
        self.uses_desktop_input = True
        self.milliseconds_list=[]
        self.regression_model_type = regression_model_type
        self.calibrate_num_points = num_points
        self.cam_id = cam_id
        self.camera_config = camera_config_from_mapping(
            {
                "camera_backend": camera_backend,
                "cam_id": cam_id,
                "camera_width": camera_width,
                "camera_height": camera_height,
                "camera_fps": camera_fps,
            },
            sys.platform,
        )
        self.camera = None
        self.start_with_calibration=start_with_calibration
        self.is_calibrating=start_with_calibration
        self.end_calibration_signal=False
        self.evaluation_stop_requested = False
        self.frame_size=None
        # 累积训练配置
        self.use_accumulated_training = use_accumulated_training
        self.max_accumulated_datasets = max_accumulated_datasets

        self.render_in_eval = render_in_eval
        self.window_name = window_name
        self.screen_size = screen_size
        self.every_point_has_n_images = every_point_has_n_images
        self.each_point_wait_time = each_point_wait_time
        self.images_freq = images_freq
        self.radius = radius
        self.edge = edge
        self.func = func
        self.data_list = []
        self.mode = 'stream'
        self.regression_model=None
        self.get_regression_model()
        
        self.regression_model_path = regression_model_path
        if self.regression_model_path is not None:
            self.load_model(self.regression_model_path)
        # self.cache_points = []
        self.kalman_filter = GazeKalmanFilter(dt, kalman_filter_std_measurement,Q_coef)
        self.include_detector = True

        # Create RetinaFace if requested
        self.gaze_bias = gaze_bias
        self.device = device
        self.weights = weights
        self.arch = arch
        
        # 眨眼检测阈值配置
        self.eye_blink_threshold = eye_blink_threshold  # 眨眼检测阈值：0.4以上算闭眼，0.4以下算睁眼
        
        # 加载模型
        self.load_model_from_weights()
        self.pred_point_color = pred_point_color  # 红色
        self.true_point_color = true_point_color  # 绿色
        self.mp_result = None  # mediapipe 输出的原始结果
        self.softmax = nn.Softmax(dim=1)
        self.predicted_position = None
        self.idx_tensor = [idx for idx in range(90)]
        self.idx_tensor = torch.FloatTensor(self.idx_tensor).to(self.device)

        self.frame = None
        self.FPS=-1
        # init a list to store frame, milliseconds
        # init a list to store step_results
        # init a list to store step_results
        self.lock = threading.Lock()
        self._lifecycle_lock = threading.RLock()

        self.open_windows = []

        self.quit = False

        self.mediapipe = self.get_mediapipe()
        self.orig_head_angles = None

    def orig_head_angles_update(self):
        try:
            head_angles = rotation_matrix_to_angles(self.mp_result.facial_transformation_matrixes[0][:3])
        except Exception as e:
            head_angles = np.array([0, 0, 0])
        self.orig_head_angles = head_angles

    def load_model_from_weights(self):
        if self.weights.endswith('.pkl') or self.weights.endswith('.pt'):
            self.model = getArch(self.arch, 90)
            self.model.load_state_dict(torch.load(self.weights, map_location=self.device),strict=True)
            self.model.to(self.device, dtype=torch.float16)
            self.model.eval()
        elif self.weights.endswith('.ts'):
            self.model = torch.jit.load(self.weights).cuda()
        elif self.weights.endswith('.param'):
            self.model=ncnn.Net()
            self.model.load_param(f"{self.weights}")
            self.model.load_model(f"{self.weights.replace('.param','.bin')}")
            self.extractor = self.model.create_extractor()
        elif self.weights.endswith('.ep'):
            self.model = torch.export.load(self.weights).module()
        else:
            raise ValueError('Unsupported weights file type')

    def step(self, frame: np.ndarray):
        with self.lock:
            pitch, yaw = self.predict_gaze(frame)
            results = IntegratedGazeResultContainer(
                pitch=pitch,
                yaw=yaw,
            )
            return results
        
    def model_inference(self,img):
        out = []
        with self.model.create_extractor() as ex:
            ex.input("in0", ncnn.Mat(img.squeeze(0).numpy()).clone())

            _, out0 = ex.extract("out0")
            out.append(torch.from_numpy(np.array(out0)).unsqueeze(0))
            _, out1 = ex.extract("out1")
            out.append(torch.from_numpy(np.array(out1)).unsqueeze(0))
        if len(out) == 1:
            return out[0]
        else:
            return tuple(out)

    def predict_gaze(self, frame: Union[np.ndarray, torch.Tensor]):
        # print(f'frame shape:{frame.shape}')
        # Prepare input
        t0=time.time()
        if isinstance(frame, np.ndarray):
            img = prep_input_numpy(frame, self.device)
        elif isinstance(frame, torch.Tensor):
            img = frame
        else:
            raise RuntimeError("Invalid dtype for input")

        t1=time.time()
        # Predict
        img = img.to(torch.float)
        gaze_pitch, gaze_yaw = self.model_inference(img)
        pitch_predicted = self.softmax(gaze_pitch)
        yaw_predicted = self.softmax(gaze_yaw)
        t2=time.time()

        # Get continuous predictions in degrees.
        pitch_predicted = torch.sum(pitch_predicted.data * self.idx_tensor, dim=1) * 4 - 180
        yaw_predicted = torch.sum(yaw_predicted.data * self.idx_tensor, dim=1) * 4 - 180

        pitch_predicted = pitch_predicted.cpu().detach().numpy() * np.pi / 180.0
        yaw_predicted = yaw_predicted.cpu().detach().numpy() * np.pi / 180.0
        t3=time.time()
        # print(f'prep_input_numpy:{t1-t0}s,model_inference:{t2-t1}s,pi:{t2-t3}s')
        return pitch_predicted, yaw_predicted

    def get_regression_model(self):
        if self.regression_model_type == 'ridge':
            self.regression_model = Ridge(alpha=1)
        elif self.regression_model_type == 'lasso':
            # 这个效果比ridge稍微好点。
            self.regression_model = Lasso(alpha=1)
        elif self.regression_model_type == 'lassocv':
            # 这个效果非常好。比较稳定，而且泛化性也好。
            self.regression_model = MultiTaskLassoCV()
        elif self.regression_model_type == 'sgd':
            self.regression_model = MultiOutputRegressor(SGDRegressor())
        elif self.regression_model_type == 'gradient_boosting':
            # 这个训练较慢，推理速度还行。
            # 推理的时候很稳定，凝视点跳动非常小。但是对有些头部姿势会导致有些屏幕区域过不去。
            # 如果数据量更大，可能效果很好。
            self.regression_model = MultiOutputRegressor(GradientBoostingRegressor())
        # 下面的算法都是试过但是效果不好的。
        elif self.regression_model_type == 'lars':
            # 这个效果就是只在屏幕四角出现，对噪声太敏感。
            self.regression_model = Lars()
        elif self.regression_model_type == 'mlp':
            # mlp没啥用
            self.regression_model = MLPRegressor(
                hidden_layer_sizes=(50, 2), max_iter=100, random_state=42)
        elif self.regression_model_type == 'random_forest':
            # 推理的时候跳动太大了。
            self.regression_model = RandomForestRegressor()
        elif self.regression_model_type == 'elastic_net':
            # 这个模型完全没用，训练出来直接在屏幕最中间怎么都不动了。
            self.regression_model = ElasticNet()
        elif self.regression_model_type == 'svr':
            self.regression_model = MultiOutputRegressor(SVR(kernel='linear'))
        elif self.regression_model_type == 'svr_sigmoid':
            # svr的效果就是根据之前的训练过的校准点进行分类，所以不能连续。
            self.regression_model = MultiOutputRegressor(SVR(kernel='sigmoid'))
        else:
            raise NotImplementedError

    def generate_calibration_points(self, **kwargs):
        if self.func == 'sequence':
            func = generate_calibration_points
        elif self.func == 'random':
            func = generate_random_calibration_points
        else:
            raise NotImplementedError
        return func(**kwargs)

    def live_stream_mp_callback(self, result, output_image: mp.Image, timestamp_ms: int):
        # print('face landmarker result: {}'.format(result))
        self.mp_result = result

    def get_mediapipe(self):
        mode = self.mode
        supported_modes = ['video', 'image', 'stream']
        assert mode in supported_modes
        if mode == 'video':
            running_mode = mp.tasks.vision.RunningMode.VIDEO
            print_result = None
        elif mode == 'image':
            running_mode = mp.tasks.vision.RunningMode.IMAGE
            print_result = None
        elif mode == 'stream':
            running_mode = mp.tasks.vision.RunningMode.LIVE_STREAM
            print_result = self.live_stream_mp_callback
        else:
            raise NotImplementedError
        # STEP 2: Create an FaceLandmarker object.
        base_options = python.BaseOptions(model_asset_path='models/face_landmarker_v2_with_blendshapes.task',
                                          )

        options = vision.FaceLandmarkerOptions(base_options=base_options,
                                               running_mode=running_mode,
                                               result_callback=print_result,
                                               output_face_blendshapes=True,
                                               output_facial_transformation_matrixes=True,
                                               num_faces=1)

        detector = vision.FaceLandmarker.create_from_options(options)
        return detector

    def smooth_position(self, pos):
        # 使用卡尔曼滤波器进行状态估计
        pos = self.kalman_filter.smooth_position(pos)
        return pos

    def get_result_mediapipe_from_image(self, image):
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image)
        mode = self.mode
        t1 = time.time()
        if mode == 'video':
            face_landmarker_result = self.mediapipe.detect_for_video(mp_image, self.milliseconds)
            self.mp_result=face_landmarker_result
        elif mode == 'image':
            face_landmarker_result = self.mediapipe.detect(mp_image)
            self.mp_result=face_landmarker_result
        elif mode == 'stream':
            # print(f'milliseconds_list:{self.milliseconds_list}')
            self.mediapipe.detect_async(mp_image, self.milliseconds)
            face_landmarker_result=self.mp_result
        else:
            raise NotImplementedError
        self.orig_head_angles_update()
        return face_landmarker_result

    def get_face_box_xxyy(self, face_landmarker_result):
        # 直接通过这个得到face的分割结果
        # 这个切割出去了额头上部和整个嘴巴。看看效果怎么样。
        points = [234, 454, 151, 200]
        boxes = []
        for i in range(len(face_landmarker_result)):
            points_xyz = face_landmarker_result[i][points]
            box = get_box_from_points(points_xyz[..., :2])
            boxes.append(box)
        return boxes

    def calibrate(self, cap: cv2.VideoCapture, test_mode=False):
        # if test_mode, we will not train regression,
        # and calculate the mean x and y error of predicted points.
        calibration_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 清空之前校准的数据，确保每次校准都是独立的
        self.data_list = []
        print(f"Started new calibration session: {calibration_time}")
        print(f"Cleared previous calibration data, starting fresh...")
        
        # store frame and ground truth
        # train
        screen_width, screen_height = self.screen_size
        every_point_has_n_images = self.every_point_has_n_images
        images_freq = self.images_freq
        each_point_wait_time = self.each_point_wait_time
        radius = self.radius
        edge = self.edge
        start_ratio = edge
        end_ratio = 1 - edge
        # 生成校准点
        calibration_points = self.generate_calibration_points(
            screen_size=self.screen_size,
            num_points=self.calibrate_num_points,
            start_ratio=start_ratio, end_ratio=end_ratio
        )

        img = np.zeros((screen_height, screen_width, 3), np.uint8)+255
        cv2.putText(img, "Calibrating", (int(screen_width / 2) - 100, int(screen_height / 2)),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        path1 = f'calibration/{calibration_time}/'
        self.calibration_time = calibration_time
        if test_mode:
            tested_true_points=[]
            tested_pred_points=[]
        
        # 使用动态校准
        return self.dynamic_calibrate(cap, calibration_points, path1, test_mode, tested_true_points if test_mode else None, tested_pred_points if test_mode else None)

    def dynamic_calibrate(self, cap: cv2.VideoCapture, calibration_points, path1, test_mode=False, tested_true_points=None, tested_pred_points=None):
        """动态校准方法，包含Tobii风格的视觉效果"""
        screen_width, screen_height = self.screen_size
        every_point_has_n_images = self.every_point_has_n_images
        images_freq = self.images_freq
        
        # 随机化校准点顺序，避免头部姿势偏移
        import random
        calibration_points = calibration_points.copy()
        random.shuffle(calibration_points)
        
        # 显示校准开始指导
        self.show_calibration_instructions()
        
        # 统计总体数据收集情况
        total_valid_photos = 0
        total_attempted_photos = 0
        points_with_no_data = []
        points_with_poor_data = []
        
        for point_idx, point in enumerate(calibration_points):
            # 检查退出条件
            if self.quit:
                print("用户要求退出，停止校准...")
                break
                
            if desktop.are_keys_down(("esc", "q")):
                print("\n用户按下 ESC+Q，退出校准...")
                self.quit = True
                break
            
            print(f"Starting calibration for point {point_idx + 1}/{len(calibration_points)}")
            
            # 校准单个点
            point_data = self.calibrate_single_point_dynamic(
                cap, point, point_idx, len(calibration_points), path1, test_mode
            )
            
            # 如果在单点校准中用户退出了，跳出主循环
            if self.quit:
                print("用户在单点校准中退出，停止整体校准...")
                break
            
            # 统计这个点的数据质量
            point_valid_photos = len(point_data)
            total_valid_photos += point_valid_photos
            
            if point_valid_photos == 0:
                points_with_no_data.append(point_idx + 1)
                print(f"ERROR: No data collected for point {point_idx + 1}")
            elif point_valid_photos < every_point_has_n_images * 0.3:
                points_with_poor_data.append(point_idx + 1)
                print(f"WARNING: Poor data collection for point {point_idx + 1} ({point_valid_photos}/{every_point_has_n_images})")
            
            # 处理收集到的数据
            for data in point_data:
                # 确保数据包含质量分数
                if 'quality_score' not in data:
                    data['quality_score'] = 0.5  # 默认中等质量
                
                
                # 如果是测试模式，记录预测点
                if test_mode and self.is_model_fitted():
                    try:
                        predicted_position = self.regression_model.predict(
                            X=self.data_dict_list_preparation_for_training_and_evaluation([data])
                        )[0]
                        tested_true_points.append(point)
                        tested_pred_points.append(predicted_position)
                    except Exception as e:
                        print(f"Error predicting for test mode: {e}")
            
            # 渐进式训练：每收集完一个点的数据就训练（如果有足够数据）
            if not test_mode and len(self.data_list) >= every_point_has_n_images:
                try:
                    print(f"Progressive training after point {point_idx + 1}...")
                    self.train_regression()
                except Exception as e:
                    print(f"Warning: Progressive training failed after point {point_idx + 1}: {e}")
        
        # 如果用户退出，直接返回None，不进行后续处理
        if self.quit:
            print("校准被用户中断，未完成...")
            return None
        
        # 汇总校准结果
        print("\n" + "="*50)
        print("CALIBRATION SUMMARY")
        print("="*50)
        print(f"Total points attempted: {len(calibration_points)}")
        print(f"Total valid photos collected: {total_valid_photos}")
        print(f"Expected photos: {len(calibration_points) * every_point_has_n_images}")
        print(f"Collection success rate: {total_valid_photos / (len(calibration_points) * every_point_has_n_images) * 100:.1f}%")
        
        if points_with_no_data:
            print(f"Points with NO data: {points_with_no_data}")
        if points_with_poor_data:
            print(f"Points with poor data: {points_with_poor_data}")
        
        # 完成校准处理
        return self.finish_calibration(path1, test_mode, tested_true_points, tested_pred_points)

    def show_calibration_instructions(self):
        """显示校准说明"""
        screen_width, screen_height = self.screen_size
        instruction_duration = 2000  # 2秒
        
        # 创建说明画面
        img = np.zeros((screen_height, screen_width, 3), np.uint8)+225
        
        # 添加说明文字（使用清晰的英文避免编码问题）
        texts = [
            "Eye Tracking Calibration",
            "",
            "Please follow these instructions:",
            "- Look at the appearing dots carefully",
            "- Keep your head still during calibration",
            "- Focus on each dot until it explodes",
            "- Keep your eyes open and relaxed",
            "- Avoid sudden head movements",
            "",
            "Calibration will start in 2 seconds..."
        ]
        
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1.0  # 稍微减小字体
        color = (255, 255, 255)
        thickness = 2
        
        # 计算总高度以居中
        total_height = len([t for t in texts if t]) * 50  # 只计算非空行
        start_y = (screen_height - total_height) // 2
        
        line_count = 0
        for text in texts:
            if text:  # 跳过空行
                text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
                x = (screen_width - text_size[0]) // 2
                y = start_y + line_count * 50
                cv2.putText(img, text, (x, y), font, font_scale, color, thickness)
                line_count += 1
        
        cv2.imshow(self.window_name, img)
        cv2.waitKey(instruction_duration)

    def shrink_point(self,screen_height, screen_width, point,duration,start_ratio=0.5,end_ratio=0.01):
        fps=20
        duration_frames=duration*fps
        for i in range(duration_frames):
            img = np.zeros((screen_height, screen_width, 3), np.uint8) + 225
            ratio = start_ratio + (end_ratio - start_ratio) * i / duration_frames
            point_size = int(screen_width * ratio)
            cv2.circle(img, point, point_size, (0, 255, 0), -1)  # 绿色目标点
            cv2.imshow(self.window_name, img)
            cv2.waitKey(int(100/fps))


    def calibrate_single_point_dynamic(self, cap: cv2.VideoCapture, point, point_idx, total_points, path1, test_mode=False):
        """校准单个点 - 简化版本"""
        screen_width, screen_height = self.screen_size
        every_point_has_n_images = self.every_point_has_n_images
        images_freq = self.images_freq
        
        point_data = []
        valid_photos_taken = 0
        
        print(f"开始校准点 {point_idx + 1}/{total_points}: {point}")
        self.shrink_point(screen_height, screen_width, point, 1)
        while valid_photos_taken < every_point_has_n_images:
            # 检查退出条件
            if desktop.are_keys_down(("esc", "q")):
                print("\n用户按下 ESC+Q，退出校准...")
                self.quit = True
                return point_data
            
            # 创建背景
            img = np.zeros((screen_height, screen_width, 3), np.uint8) + 225
            
            # 1. 先检测眼睛状态
            if self.check_eyes_closed():
                # 眼睛闭合，显示提示并跳过
                cv2.circle(img, point, 50, (0, 0, 255), 3)
                cv2.putText(img, "EYES CLOSED - PLEASE OPEN EYES", (50, 100), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                cv2.imshow(self.window_name, img)
                cv2.waitKey(30)
                continue
            
            # 2. 眼睛张开，获取数据并保存
            results = self.get_results_from_capture()
            if results is None:
                continue
                
            results_dict = self.results_to_data_dict(results)
                
            # 保存图像和数据
            image_path = path1 + f'images/{point_idx}_{valid_photos_taken}.png'
            os.makedirs(os.path.dirname(image_path), exist_ok=True)
            cv2.imwrite(image_path, self.frame)
                
            results_dict['target_point'] = point
            results_dict['label'] = point
            results_dict['image_path'] = image_path
            self.data_list.append(results_dict.copy())
            point_data.append(results_dict.copy())
            valid_photos_taken += 1
                
            print(f"收集数据: {valid_photos_taken}/{every_point_has_n_images}")
                
            # 增量训练
            if len(self.data_list) % 5 == 0:
                try:
                    self.train_regression()
                    print(f"模型训练更新: {len(self.data_list)} 样本")
                except Exception as e:
                    print(f"训练失败: {e}")
                
            # 5. 显示预测结果（如果有模型）
            if point_idx > 0 and hasattr(self, 'regression_model') and self.regression_model:
                try:
                    predicted_position = self.regression_model.predict(
                        X=self.data_dict_list_preparation_for_training_and_evaluation([results_dict])
                    )
                    if predicted_position is not None and len(predicted_position) > 0:
                        pred_x, pred_y = int(predicted_position[0][0]), int(predicted_position[0][1])
                        pred_x = max(0, min(screen_width - 1, pred_x))
                        pred_y = max(0, min(screen_height - 1, pred_y))
                            
                        # 绘制预测点
                        cv2.circle(img, (pred_x, pred_y), 2, (0, 50, 50), -1)
                        cv2.putText(img, "Predicted", (pred_x + 15, pred_y),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5,  (0, 50, 50), 1)
                            
                        # 显示误差
                        distance = np.sqrt((pred_x - point[0])**2 + (pred_y - point[1])**2)
                        cv2.putText(img, f"Error: {distance:.1f}px", (pred_x + 15, pred_y + 20),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 50, 50), 1)
                except Exception as e:
                    print(f"预测错误: {e}")
                
            time.sleep(1.0 / images_freq)  # 控制采样频率
                
            # 6. 绘制界面
            # 绘制目标点
            point_size=np.random.randint(20, 40)
            cv2.circle(img, point, point_size, (0, 255, 0), -1)  # 绿色目标点
            
            # 显示进度
            progress_text = f"Point {point_idx + 1}/{total_points}: {valid_photos_taken}/{every_point_has_n_images}"
            cv2.putText(img, progress_text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # 显示状态
            status_text = "COLLECTING DATA - Eyes Open"
            cv2.putText(img, status_text, (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            
            # 退出提示
            cv2.putText(img, "Press ESC+Q to quit", (50, screen_height - 50), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            cv2.imshow(self.window_name, img)
            key = cv2.waitKey(30)
            
            if key == 27:  # ESC键
                print("\n用户按下 ESC 键，退出校准...")
                self.quit = True
                return point_data
        
        print(f"点 {point_idx + 1} 完成: {valid_photos_taken} 张有效照片")
        return point_data

    def calculate_eye_aspect_ratio(self, eye_points):
        """
        计算眼睛纵横比 (Eye Aspect Ratio - EAR)
        基于 Soukupová & Čech (2016) 的研究
        """
        try:
            # 眼睛的6个关键点：左右眼角 + 上下眼睑的4个点
            if len(eye_points) < 6:
                return 0.2  # 默认值
            
            # 计算垂直距离 (上下眼睑)
            vertical_1 = np.linalg.norm(eye_points[1] - eye_points[5])
            vertical_2 = np.linalg.norm(eye_points[2] - eye_points[4])
            
            # 计算水平距离 (左右眼角)
            horizontal = np.linalg.norm(eye_points[0] - eye_points[3])
            
            # EAR计算
            if horizontal > 0:
                ear = (vertical_1 + vertical_2) / (2.0 * horizontal)
                return ear
            else:
                return 0.2
        except Exception as e:
            print(f"Error during eye aspect ratio calculation: {e}")
            return 0.2
        
    def validate_training_data(self):
        """
        验证训练数据的有效性
        """
        try:
            if not self.data_list:
                return False
            
            # 检查数据结构完整性
            required_keys = ['mediapipe_results', 'label']
            for i, data in enumerate(self.data_list):
                for key in required_keys:
                    if key not in data:
                        print(f"Missing key '{key}' in data sample {i}")
                        return False
                
                # 检查mediapipe结果的形状
                try:
                    mp_results = np.array(data['mediapipe_results'])
                    if mp_results.shape != (478, 3):  # MediaPipe面部关键点应该是478个点，每个3D坐标
                        print(f"Invalid mediapipe_results shape in sample {i}: {mp_results.shape}, expected (478, 3)")
                        return False
                except:
                    print(f"Invalid mediapipe_results format in sample {i}")
                    return False
                
                # 检查标签的有效性
                try:
                    label = data['label']
                    if not isinstance(label, (list, tuple)) or len(label) != 2:
                        print(f"Invalid label format in sample {i}: {label}")
                        return False
                    
                    x, y = label
                    if not (0 <= x <= self.screen_size[0] and 0 <= y <= self.screen_size[1]):
                        print(f"Label out of screen bounds in sample {i}: {label}")
                        return False
                except:
                    print(f"Invalid label in sample {i}")
                    return False
            
            # 检查数据的多样性（避免所有数据都指向相同位置）
            labels = np.array([data['label'] for data in self.data_list])
            unique_labels = np.unique(labels, axis=0)
            
            if len(unique_labels) < self.calibrate_num_points * 0.8:  # 至少80%的校准点应该有数据
                print(f"Insufficient label diversity: only {len(unique_labels)} unique positions out of {self.calibrate_num_points} calibration points")
                return False
            
            print("Training data validation passed")
            return True
            
        except Exception as e:
            print(f"Error during data validation: {e}")
            return False
    
    def show_calibration_failure(self, message):
        """显示校准失败消息"""
        screen_width, screen_height = self.screen_size
        img = np.zeros((screen_height, screen_width, 3), np.uint8)+225
        
        # 绘制失败消息
        lines = message.split('\n')
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1.2
        thickness = 2
        line_height = 40
        
        # 计算总文本高度并居中
        total_height = len(lines) * line_height
        start_y = (screen_height - total_height) // 2 + 100
        
        for i, line in enumerate(lines):
            text_size = cv2.getTextSize(line, font, font_scale, thickness)[0]
            x = (screen_width - text_size[0]) // 2
            y = start_y + i * line_height
            cv2.putText(img, line, (x, y), font, font_scale, (0, 0, 255), thickness)
        
        # 绘制失败标记 (X)
        x_size = 80
        x_center_x = screen_width // 2
        x_center_y = screen_height // 2 - 150
        
        # 绘制圆形背景
        cv2.circle(img, (x_center_x, x_center_y), x_size, (0, 0, 255), 5)
        
        # 绘制X
        cv2.line(img, (x_center_x - 40, x_center_y - 40), (x_center_x + 40, x_center_y + 40), (0, 0, 255), 8)
        cv2.line(img, (x_center_x - 40, x_center_y + 40), (x_center_x + 40, x_center_y - 40), (0, 0, 255), 8)
        
        # 添加重试提示
        retry_text = "Press any key to continue..."
        text_size = cv2.getTextSize(retry_text, font, 0.8, 2)[0]
        retry_x = (screen_width - text_size[0]) // 2
        retry_y = start_y + len(lines) * line_height + 50
        cv2.putText(img, retry_text, (retry_x, retry_y), font, 0.8, (255, 255, 255), 2)
        
        cv2.imshow(self.window_name, img)
        cv2.waitKey(0)  # 等待用户按键

    def show_calibration_success(self):
        """显示校准成功消息"""
        screen_width, screen_height = self.screen_size
        img = np.zeros((screen_height, screen_width, 3), np.uint8)+225
        
        # 绘制成功消息
        success_text = "Calibration Completed Successfully!"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1.5
        thickness = 3
        
        text_size = cv2.getTextSize(success_text, font, font_scale, thickness)[0]
        x = (screen_width - text_size[0]) // 2
        y = (screen_height + text_size[1]) // 2
        
        cv2.putText(img, success_text, (x, y), font, font_scale, (0, 255, 0), thickness)
        
        # 绘制检查标记
        check_size = 100
        check_x = screen_width // 2
        check_y = screen_height // 2 - 100
        
        # 绘制圆形背景
        cv2.circle(img, (check_x, check_y), check_size, (0, 255, 0), 5)
        
        # 绘制对勾
        pts = np.array([
            [check_x - 30, check_y],
            [check_x - 10, check_y + 20],
            [check_x + 30, check_y - 20]
        ], np.int32)
        cv2.polylines(img, [pts], False, (0, 255, 0), 8)
        
        cv2.imshow(self.window_name, img)
        cv2.waitKey(2000)  # 显示2秒

    def process_test_mode_results(self, path1, tested_true_points, tested_pred_points):
        """处理测试模式的结果"""
        # 这里保持原有的测试模式逻辑
        tested_true_points = np.array(tested_true_points)
        tested_pred_points = np.array(tested_pred_points)
        
        # 获取唯一的真实点位置
        unique_true_points = np.unique(tested_true_points, axis=0)
        point_errors = []
        
        # 计算每个校准点的平均误差
        for true_point in unique_true_points:
            # 找到所有对应这个真实点的预测点
            mask = np.all(tested_true_points == true_point, axis=1)
            corresponding_preds = tested_pred_points[mask]
            
            # 计算这个点的平均欧氏距离误差(MED)
            point_med = np.mean(np.sqrt(np.sum((corresponding_preds - true_point) ** 2, axis=1)))
            point_errors.append((true_point[0], true_point[1], point_med))
        
        point_errors = np.array(point_errors)
        
        # 创建可视化
        plt.figure(figsize=(12, 8))
        
        # 使用二次多项式拟合误差分布
        # 创建网格点进行插值
        grid_x, grid_y = np.mgrid[0:self.screen_size[0]:100j, 0:self.screen_size[1]:100j]
        
        # 使用径向基函数进行插值
        from scipy.interpolate import Rbf
        rbf = Rbf(point_errors[:, 0], point_errors[:, 1], point_errors[:, 2], 
                 function='gaussian', smooth=1)
        grid_z = rbf(grid_x, grid_y)
        
        # 先绘制填充的彩色等高线图
        contourf = plt.contourf(grid_x, grid_y, grid_z,
                              levels=15,  # 增加等级数使颜色过渡更平滑
                              cmap='YlOrRd',  # 使用从黄到橙到红的颜色图
                              alpha=0.7)  # 稍微调整透明度
        
        # 添加颜色条
        plt.colorbar(contourf, label='Error (pixels)')
        
        # 在彩色图上叠加等高线
        contour = plt.contour(grid_x, grid_y, grid_z, 
                            levels=10, 
                            colors='k',  # 黑色等高线
                            alpha=0.3,
                            linewidths=0.8)  # 适当调整线宽
        plt.clabel(contour, inline=True, fontsize=8, fmt='%.0f')
        
        plt.title('Gaze Prediction Error Distribution\n' + 
                 f'Overall Mean Error: {np.mean(point_errors[:, 2]):.2f}px')
        plt.xlabel('Screen X Position (pixels)')
        plt.ylabel('Screen Y Position (pixels)')
        
        # 设置坐标轴范围为屏幕分辨率
        plt.xlim(0, self.screen_size[0])
        plt.ylim(0, self.screen_size[1])
        
        # 添加网格
        plt.grid(True, alpha=0.2)
        
        # 保存图像
        plt.savefig(path1 + 'gaze_error_distribution.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 计算并打印整体误差统计
        mse_x = np.mean(np.abs(tested_true_points[:,0]-tested_pred_points[:,0]))
        mse_y = np.mean(np.abs(tested_true_points[:,1]-tested_pred_points[:,1]))
        med = np.mean(np.sqrt(np.sum((tested_true_points - tested_pred_points) ** 2, axis=1)))
        
        # 保存误差统计和测试点数据
        error_stats = {
            'statistics': {
                'mse_x': float(mse_x),
                'mse_y': float(mse_y),
                'med': float(med),
            },
            'point_data': {
                'true_points': tested_true_points.tolist(),
                'pred_points': tested_pred_points.tolist(),
            },
            'error_distribution': {
                'points': point_errors.tolist(),  # 包含 [x, y, error] 的列表
            }
        }
        
        # 保存误差统计数据
        with open(path1 + 'error_statistics.json', 'w') as f:
            json.dump(error_stats, f, indent=4)


    def check_eyes_closed(self):
        """检测眼睛是否闭合 - 使用已有的mp_result"""
        return False
        # try:
        #     # 直接使用live_stream_mp_callback更新的mp_result
        #     if not hasattr(self, 'mp_result') or not self.mp_result:
        #         return True  # 没有MediaPipe结果时认为眼睛闭合
            
        #     if hasattr(self.mp_result, 'face_blendshapes') and self.mp_result.face_blendshapes:
        #         face_blendshapes = self.mp_result.face_blendshapes[0]
        #         face_blendshapes_names = [category.category_name for category in face_blendshapes]
        #         face_blendshapes_scores = [category.score for category in face_blendshapes]
        #         blendshapes_dict = dict(zip(face_blendshapes_names, face_blendshapes_scores))
                
        #         eye_blink_left = blendshapes_dict.get('eyeBlinkLeft', 0.0)
        #         eye_blink_right = blendshapes_dict.get('eyeBlinkRight', 0.0)
        #         max_eye_blink = max(eye_blink_left, eye_blink_right)
                
        #         return max_eye_blink > self.eye_blink_threshold
            
        #     return False  # 无法检测时认为眼睛闭合
            
        # except Exception as e:
        #     print(f"Eye detection error: {e}")
        #     return True  # 检测失败时认为眼睛闭合

    def update_gaze_stability(self, current_gaze, target_point, stability_buffer, last_valid_gaze):
        """更新注视稳定性"""
        stability_window = 10  # 用于计算稳定性的窗口大小
        max_distance = 100  # 最大允许距离（像素）
        
        if current_gaze is not None:
            # 计算到目标点的距离
            distance = np.sqrt((current_gaze[0] - target_point[0])**2 + (current_gaze[1] - target_point[1])**2)
            stability_score = max(0, 1 - distance / max_distance)
            stability_buffer.append(stability_score)
        elif last_valid_gaze is not None:
            # 如果当前没有有效注视，使用上次的结果计算
            distance = np.sqrt((last_valid_gaze[0] - target_point[0])**2 + (last_valid_gaze[1] - target_point[1])**2)
            stability_score = max(0, 1 - distance / max_distance) * 0.5  # 降权
            stability_buffer.append(stability_score)
        else:
            stability_buffer.append(0)
        
        # 保持缓冲区大小
        if len(stability_buffer) > stability_window:
            stability_buffer.pop(0)
        
        # 计算平均稳定性
        if stability_buffer:
            return np.mean(stability_buffer)
        return 0
    def results_to_data_dict(self, results):
        # print(results)
        screen_width, screen_height = self.screen_size
        # print(f'results.bboxes:{type(results.bboxes)}')
        pitch = results.pitch.tolist()[0]
        yaw = results.yaw.tolist()[0]
        # 不知道为什么这个bboxes就会变成list，就是step传出来之后就有概率变成list。
        # 我难评了，直接加个条件判断解决

        return {
            'pitch': pitch,
            'yaw': yaw,
            'box': results.bboxes[0],
            'mediapipe_results': results.landmarks[0].tolist(),
            'head_angles': results.head_angles.tolist(),
        }

    def data_dict_list_preparation_for_training_and_evaluation(self, data_dict_list, include_labels=False):
        points = [234, 454, 151, 200]
        X = [[*data['box'], *np.array(data['mediapipe_results'])[points, -1].tolist(), data['yaw'], data['pitch'],
        # np.sin(data['yaw']), np.cos(data['yaw']), np.sin(data['pitch']), np.cos(data['pitch']),
        # np.sin(data['pitch']) * np.cos(data['yaw']), np.cos(data['pitch']) * np.sin(data['yaw']),
        # np.sin(data['pitch']) * np.sin(data['yaw']), np.cos(data['pitch']) * np.cos(data['yaw']),
        # np.sin(data['pitch']) * np.sin(data['pitch']), np.sin(data['yaw']) * np.sin(data['yaw']),
        # *data['head_angles']

        ] for data in data_dict_list]
        X = np.array(X)
        if include_labels:
            y = [[*point['label']] for point in data_dict_list]
            y = np.array(y)
            return X, y
        return X

    def cap_read_img(self):
        self.frame = self.camera.read()
        milliseconds = time.monotonic_ns() // 1_000_000
        if self.milliseconds_list:
            # MediaPipe requires strictly increasing integer milliseconds.
            # Consecutive camera frames can share one quantized millisecond.
            milliseconds = max(
                milliseconds,
                self.milliseconds_list[-1] + 1,
            )
        self.milliseconds = milliseconds
        self.milliseconds_list.append(milliseconds)
        self.milliseconds_list = self.milliseconds_list[-10:]

    def get_results_from_capture(self):
        count = 0
        while 1:
            t00 = time.time()
            self.cap_read_img()
            frame = self.frame
            if self.frame_size is None:
                self.frame_size = frame.shape[:2]
            t0 = time.time()
            # 获取MediaPipe原结果
            mp_result = self.get_result_mediapipe_from_image(image=frame)
            if mp_result is None or not mp_result.face_landmarks:
                continue
            
            # 从MediaPipe结果提取landmarks
            landmarks = get_all_landmark_from_result(result=mp_result)
            if landmarks is None or len(landmarks) == 0:
                continue
            
            self.mediapipe_results_in_numpy = landmarks
            
            t1 = time.time()
            face_num = landmarks.shape[0]
            if face_num == 0 or face_num > 1:
                continue
            
            # 计算脸部边界框（0-1范围）
            points = [234, 454, 151, 200]  # 脸部关键点索引
            points_xyz = landmarks[0][points]  # 第一个脸
            bbox = get_box_from_points(points_xyz[..., :2])  # [xmin, xmax, ymin, ymax] 0-1范围
            
            # 转换为像素坐标并裁剪脸部图像
            h, w = frame.shape[:2]
            xmin, xmax, ymin, ymax = bbox
            x1, x2 = int(xmin * w), int(xmax * w)
            y1, y2 = int(ymin * h), int(ymax * h)
            
            # 确保边界框在图像范围内
            x1, x2 = max(0, x1), min(w, x2)
            y1, y2 = max(0, y1), min(h, y2)
            
            # 裁剪脸部图像
            face_crop = frame[y1:y2, x1:x2]
            if face_crop.size == 0:
                continue
            
            # 将裁剪的脸部图像传给self.step
            results = self.step(face_crop)
            if results is None:
                continue
            
            # 构建结果容器
            results = AllResultContainer(
                pitch=results.pitch,
                yaw=results.yaw,
                bboxes=[bbox],  # 边界框格式 [xmin, xmax, ymin, ymax]
                landmarks=landmarks,
                head_angles=self.orig_head_angles,
            )
            
            t2 = time.time()
            if count >= 1:
                time.sleep(count)
            if face_num == 1:
                break
            count += 1
        return results

    def train_lot_data(self, jsonl_path_list: list, model_save_path):
        # 合并所有jsonl
        all_json_data = []
        for i, json_path in enumerate(jsonl_path_list):
            json_data = read_jsonlines(json_path)
            all_json_data.extend(json_data)
        self.train_regression(data_list=all_json_data)
        self.save_model(model_save_path=model_save_path)
        self.load_model(model_save_path=model_save_path)

    def train_regression(self, data_list=None, reset=False):
        if data_list is None:
            data_list = self.data_list
        if reset:
            self.get_regression_model()
        X, y = self.data_dict_list_preparation_for_training_and_evaluation(data_list, include_labels=True)
        self.regression_model.fit(X, y)

    def get_screen_resolution(self):
        return desktop.get_screen_size()

    def call_after_each_eval_loop(self):
        # can be used for multiprocessing processes
        pass

    def call_before_while_loop(self):
        # can be used for multiprocessing init
        pass

    def call_after_while_loop(self):
        # can be used for end multiprocessing
        pass

    def setup_window(self):
        screen_width, screen_height = self.screen_size
        first_frame = np.full(
            (screen_height, screen_width, 3),
            225,
            dtype=np.uint8,
        )
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.imshow(self.window_name, first_frame)
        cv2.waitKey(1)
        cv2.moveWindow(self.window_name, x=0, y=0)
        # Xorg applies the move asynchronously. Qt5 ignores a fullscreen
        # request sent before the window manager has processed that move.
        cv2.waitKey(100)
        cv2.setWindowProperty(
            self.window_name,
            cv2.WND_PROP_FULLSCREEN,
            cv2.WINDOW_FULLSCREEN,
        )
        cv2.waitKey(100)
        fullscreen = cv2.getWindowProperty(
            self.window_name,
            cv2.WND_PROP_FULLSCREEN,
        )
        if fullscreen != float(cv2.WINDOW_FULLSCREEN):
            raise RuntimeError(
                f"calibration window {self.window_name!r} did not enter "
                f"fullscreen; OpenCV reported {fullscreen!r}"
            )
        self.open_windows.append(self.window_name)

    def destroy_window(self):
        cv2.destroyAllWindows()
        self.open_windows.clear()


    
    
    def start_service(self):
        with self._lifecycle_lock:
            if self.quit:
                raise RuntimeError("pipeline has been shut down")
            if self.camera is not None:
                raise RuntimeError("camera service is already started")
            self.screen_size = self.get_screen_resolution()
            self.mid_point = (self.screen_size[0] // 2, self.screen_size[1] // 2)
            self.camera = open_camera(self.camera_config, sys.platform)

    def _close_camera(self):
        if self.camera is None:
            return
        camera = self.camera
        camera.close()
        self.camera = None

    def _finish_run(self):
        with self._lifecycle_lock:
            if self.quit:
                return
            if hasattr(self, "gaze_mouse_controller"):
                self.gaze_mouse_controller.stop()
            self._close_camera()
            self.destroy_window()

    def start_calibration(self):
        cancelled = False
        completed = None
        try:
            with self._lifecycle_lock:
                if self.quit:
                    raise RuntimeError("pipeline has been shut down")
                if self.camera is None:
                    self.start_service()
                self.setup_window()
                cv2.waitKey(2000)
                if self.quit:
                    cancelled = True
                else:
                    completed = self.calibrate(self.camera)
                self.is_calibrating = False
                cancelled = cancelled or self.quit
            if not cancelled:
                self._finish_run()
        except BaseException as error:
            self.quit_pipeline(error)
        if cancelled:
            self.quit_pipeline()
            return None
        return completed

    def end_calibration(self):
        self.end_calibration_signal = True

    def request_evaluation_stop(self):
        """Interrupt a blocking camera read from the supervisor thread."""
        self.evaluation_stop_requested = True
        self.end_calibration_signal = True
        camera = self.camera
        if camera is not None:
            camera.close()

    def start_evaluation(self):
        try:
            count = 0
            tl = []
            first_iteration = True
            self.end_calibration_signal = False
            while True:
                with self._lifecycle_lock:
                    if first_iteration:
                        if self.evaluation_stop_requested:
                            break
                        if self.quit:
                            raise RuntimeError("pipeline has been shut down")
                        if self.camera is None:
                            self.start_service()
                        self.call_before_while_loop()
                    if self.quit:
                        break
                    t_start = time.time()
                    if self.render_in_eval and len(self.open_windows) == 0:
                        self.setup_window()
                    self.evaluate(self.camera)
                first_iteration = False
                if self.quit:
                    break
                cv2.waitKey(1)
                if self.quit or self.end_calibration_signal:
                    break
                t_end = time.time()
                count += 1
                tl.append(t_end - t_start)
                used_tl = tl[-60:]
                per_duration = sum(used_tl) / len(used_tl)
                self.FPS = 1 / per_duration
                with self._lifecycle_lock:
                    if self.quit:
                        break
                    self.call_after_each_eval_loop()
            with self._lifecycle_lock:
                if not self.quit:
                    self.call_after_while_loop()
                    self._finish_run()
        except BaseException as error:
            if self.evaluation_stop_requested:
                try:
                    self.quit_pipeline()
                except BaseException as cleanup_error:
                    cleanup_error.add_note(
                        "camera read was interrupted by an explicit "
                        f"evaluation stop request: {type(error).__name__}: "
                        f"{error}"
                    )
                    raise
                return
            self.quit_pipeline(error)

    def quit_pipeline(self, primary_error: BaseException | None = None):
        """Stop pipeline-owned resources without closing the shared desktop."""
        self.quit = True
        self.end_calibration_signal = True
        with self._lifecycle_lock:
            primary_traceback = (
                primary_error.__traceback__ if primary_error is not None else None
            )

            cleanup_errors = []

            def cleanup(operation, callback):
                try:
                    callback()
                except BaseException as error:
                    cleanup_errors.append((operation, error))

            if hasattr(self, "wheel"):
                cleanup(
                    "wheel.stop",
                    self.wheel.stop,
                )

            if hasattr(self, "_discard_actions"):
                cleanup("action discard", self._discard_actions)

            if self.uses_desktop_input:
                cleanup("desktop.release_all", desktop.release_all)
            if hasattr(self, "gaze_mouse_controller"):
                cleanup(
                    "gaze_mouse_controller.stop",
                    self.gaze_mouse_controller.stop,
                )
            if hasattr(self, "_stop_gaze_display"):
                cleanup(
                    "gaze_overlay.stop",
                    self._stop_gaze_display,
                )
            cleanup("camera.close", self._close_camera)
            cleanup("destroy_window", self.destroy_window)

            if primary_error is not None:
                for operation, error in cleanup_errors:
                    primary_error.add_note(
                        f"{operation} failed with "
                        f"{type(error).__name__}: {error}"
                    )
                raise primary_error.with_traceback(primary_traceback)
            if cleanup_errors:
                raise BaseExceptionGroup(
                    "pipeline cleanup failed",
                    [error for _, error in cleanup_errors],
                )

    def enter_calibration(self):
        self.is_calibrating = True

    def enter_evaluation(self):
        self.is_calibrating = False

    def is_model_fitted(self):
        """检查回归模型是否已经训练"""
        if self.regression_model is None:
            return False
            
        # 根据不同类型的回归模型检查不同的属性
        if hasattr(self.regression_model, 'coef_'):  # LinearRegression, Ridge, Lasso
            return True
        if hasattr(self.regression_model, 'dual_coef_'):  # SVR
            return True
        if hasattr(self.regression_model, 'tree_'):  # DecisionTreeRegressor
            return True
        if hasattr(self.regression_model, 'estimators_'):  # RandomForestRegressor
            return True
        
        return False
    def demo(self):
        cancelled = False
        try:
            is_calibrating = self.start_with_calibration
            is_testing = False
            count = 0
            tl = []
            first_iteration = True
            while True:
                with self._lifecycle_lock:
                    if first_iteration:
                        if self.quit:
                            raise RuntimeError("pipeline has been shut down")
                        if self.camera is None:
                            self.start_service()
                        self.call_before_while_loop()
                    if self.quit:
                        cancelled = True
                        break
                    t_start = time.time()
                    if is_calibrating:
                        print("start calibrating")
                        self.setup_window()
                        cv2.waitKey(2000)
                        if self.quit:
                            cancelled = True
                            break
                        self.calibrate(self.camera, test_mode=is_testing)
                        if self.quit:
                            cancelled = True
                            break
                        is_calibrating = False
                        is_testing = False
                        self.destroy_window()
                    else:
                        if self.render_in_eval and len(self.open_windows) == 0:
                            self.setup_window()
                        self.evaluate(self.camera)
                first_iteration = False
                if self.quit:
                    cancelled = True
                    break
                cv2.waitKey(1)
                if self.quit:
                    cancelled = True
                    break
                if desktop.are_keys_down(("esc", "q")):
                    cancelled = True
                    break
                if desktop.are_keys_down(("esc", "r")):
                    is_calibrating = True
                elif desktop.are_keys_down(("esc", "t")):
                    is_calibrating = True
                    is_testing = True

                t_end = time.time()
                count += 1
                tl.append(t_end - t_start)
                used_tl = tl[-60:]
                per_duration = sum(used_tl) / len(used_tl)
                self.FPS = 1 / per_duration
                print(
                    f"FPS: {self.FPS:.2f} duration: {per_duration:.2f}"
                )
                with self._lifecycle_lock:
                    if self.quit:
                        cancelled = True
                        break
                    self.call_after_each_eval_loop()
            with self._lifecycle_lock:
                if not cancelled and not self.quit:
                    self.call_after_while_loop()
                    self._finish_run()
        except BaseException as error:
            self.quit_pipeline(error)
        if cancelled:
            self.quit_pipeline()
        return None

    def save_model(self, model_save_path=None):
        if model_save_path is None:
            model_save_path = 'model_weights/' + self.calibration_time + '/model.pkl'
        os.makedirs(os.path.dirname(model_save_path), exist_ok=True)
        with open(model_save_path, 'wb') as f:
            pickle.dump(self.regression_model, f)
        print(f"Model saved at {model_save_path}")

    def load_model(self, model_save_path):
        with open(model_save_path, 'rb') as file:
            loaded_model = pickle.load(file)
        self.regression_model = loaded_model

    def evaluate(self, cap):
        t0 = time.time()
        results = self.get_results_from_capture()
        # print(results)
        t1 = time.time()
        results_dict = self.results_to_data_dict(results)
        t2 = time.time()
        predicted_position = self.regression_model.predict(
            X=self.data_dict_list_preparation_for_training_and_evaluation([results_dict], ))
        # print(f'predicted_position:{predicted_position}')
        t3 = time.time()
        predicted_position = predicted_position[0]
        predicted_position = self.smooth_position(predicted_position)
        predicted_position = [predicted_position[0] + self.gaze_bias[0], predicted_position[1] + self.gaze_bias[1]]
        t4 = time.time()
        # pred_points 才需要这样搞
        pred_points = [np.clip(predicted_position[0], 0, self.screen_size[0]),
                       np.clip(predicted_position[1], 0, self.screen_size[1])]
        # print(f'pred_points:{pred_points}')
        self.predicted_position = predicted_position
        results.bboxes = [[b[0], b[2], b[1], b[3]] for b in results.bboxes]
        t5 = time.time()
        if self.render_in_eval:
            self.render(cap_frame=self.frame, results=results, pred_points=pred_points)
        t6 = time.time()

    def render(self, cap_frame=None, results=None, pred_points=None, true_points=None, frame=None, show_at_last=True):
        if frame is None:
            # 如果没有传入最初的图像，就会直接创建空白屏幕
            frame = np.zeros((self.screen_size[1], self.screen_size[0], 3), np.uint8)+225
        if cap_frame is not None and results is not None:
            # 如果想要把摄像头的图像放上去就要输入这个参数
            labeled_frame = render(cap_frame, results)
            frame = resize_and_place_image(small_img=labeled_frame, big_img=frame, scale_fraction=1 / 3)
        if pred_points is not None:
            cv2.circle(frame, (int(pred_points[0]), int(pred_points[1])), self.radius, self.pred_point_color, -1)
        if true_points is not None:
            cv2.circle(frame, (int(true_points[0]), int(true_points[1])), self.radius, self.true_point_color, -1)
        if show_at_last:
            cv2.imshow(self.window_name, frame)

    def finish_calibration(self, path1, test_mode, tested_true_points, tested_pred_points):
        """完成校准的处理 - 包含质量报告生成和累积训练支持"""
        if not hasattr(self, 'data_list') or not self.data_list:
            print("Warning: No calibration data collected!")
            self.show_calibration_failure("No calibration data was collected. Please try again.")
            return None

        self.generate_quality_report(path1)
        self.save_calibration_data(path1)

        if test_mode:
            return self.process_test_mode_results(path1, tested_true_points, tested_pred_points)

        if not self.validate_training_data():
            print("Error: Training data validation failed!")
            self.show_calibration_failure("Training data validation failed.\nData appears to be corrupted or incomplete.")
            return None

        if self.use_accumulated_training:
            print("Using accumulated training with historical data...")
            training_success = self.train_with_accumulated_data(
                current_calibration_path=path1,
                max_datasets=self.max_accumulated_datasets,
            )
        else:
            if len(self.data_list) != self.calibrate_num_points * self.every_point_has_n_images:
                raise Exception(f"数据量不足，需要{self.num_points*self.every_point_has_n_images}条数据，但只有{len(self.data_list)}条数据")
            print("Using current calibration data only...")
            self.train_regression(reset=True)
            training_success = self.is_model_fitted()

        if not training_success:
            print("Error: Model training failed!")
            self.show_calibration_failure("Model training failed.\nPlease try calibration again.")
            return None

        self.save_model()
        print("Model training completed successfully!")
        self.show_calibration_success()
        return True

    def generate_quality_report(self, path1):
        """生成详细的质量报告"""
        try:
            print("Generating quality report...")
            
            # 收集所有质量分数
            quality_scores = [data.get('quality_score', 0.0) for data in self.data_list]
            total_samples = len(self.data_list)
            
            if total_samples == 0:
                print("Warning: No data available for quality report")
                return
            
            # 基于新门槛式系统的质量统计
            # 门槛式系统中，质量分数要么是0（失败），要么是0.6-1.0（通过）
            passed_samples = sum(1 for score in quality_scores if score > 0.0)
            failed_samples = total_samples - passed_samples
            
            # 对通过的样本进行进一步分类
            excellent_samples = sum(1 for score in quality_scores if score >= 0.9)
            good_samples = sum(1 for score in quality_scores if 0.8 <= score < 0.9)
            fair_samples = sum(1 for score in quality_scores if 0.6 <= score < 0.8)
            
            # 计算统计信息
            avg_quality = np.mean(quality_scores)
            median_quality = np.median(quality_scores)
            min_quality = np.min(quality_scores)
            max_quality = np.max(quality_scores)
            
            # 收集每个校准点的统计信息
            point_stats = {}
            for data in self.data_list:
                point = tuple(data.get('target_point', (0, 0)))
                if point not in point_stats:
                    point_stats[point] = {'count': 0, 'scores': [], 'avg_score': 0.0}
                point_stats[point]['count'] += 1
                point_stats[point]['scores'].append(data.get('quality_score', 0.0))
            
            # 计算每个点的平均质量
            for point in point_stats:
                point_stats[point]['avg_score'] = np.mean(point_stats[point]['scores'])
            
            # 创建质量报告
            quality_report = {
                'generation_time': datetime.now().isoformat(),
                'evaluation_system': 'gating_based',  # 门槛式系统
                'total_statistics': {
                    'total_samples': total_samples,
                    'passed_samples': passed_samples,
                    'failed_samples': failed_samples,
                    'pass_rate': passed_samples / total_samples if total_samples > 0 else 0.0,
                    'average_quality': float(avg_quality),
                    'median_quality': float(median_quality),
                    'min_quality': float(min_quality),
                    'max_quality': float(max_quality),
                },
                'quality_distribution': {
                    'failed_gates': failed_samples,
                    'fair_0.6-0.8': fair_samples,
                    'good_0.8-0.9': good_samples,
                    'excellent_0.9+': excellent_samples,
                },
                'quality_thresholds': {
                    'face_detection': 'Required (gate)',
                    'eyes_open': f'BlinkMax < {self.eye_blink_threshold} (gate)',
                    'image_available': 'Required (gate)',
                    'overall_threshold': 'All gates must pass',
                },
                'per_point_statistics': {},
                'data_collection_summary': {
                    'expected_points': self.calibrate_num_points,
                    'actual_points': len(point_stats),
                    'expected_samples_per_point': self.every_point_has_n_images,
                    'samples_per_point': {}
                }
            }
            
            # 添加每个点的详细信息
            for point, stats in point_stats.items():
                point_key = f"{point[0]:.0f},{point[1]:.0f}"
                quality_report['per_point_statistics'][point_key] = {
                    'samples_collected': stats['count'],
                    'average_quality': float(stats['avg_score']),
                    'quality_scores': [float(score) for score in stats['scores']],
                    'pass_rate': sum(1 for score in stats['scores'] if score > 0.0) / len(stats['scores'])
                }
                quality_report['data_collection_summary']['samples_per_point'][point_key] = stats['count']
            
            # 添加系统信息
            quality_report['system_info'] = {
                'calibration_time': getattr(self, 'calibration_time', 'unknown'),
                'screen_resolution': list(self.screen_size),
                'calibration_points': self.calibrate_num_points,
                'samples_per_point': self.every_point_has_n_images,
                'sampling_frequency': self.images_freq,
                'evaluation_method': 'MediaPipe BlendShapes + Gating Logic'
            }
            
            # 保存质量报告
            report_path = path1 + 'quality_report.json'
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            with open(report_path, 'w') as f:
                json.dump(quality_report, f, indent=4)
            
            # 打印简要报告
            print("="*50)
            print("QUALITY REPORT SUMMARY")
            print("="*50)
            print(f"Total samples: {total_samples}")
            print(f"Passed quality gates: {passed_samples} ({passed_samples/total_samples*100:.1f}%)")
            print(f"Failed quality gates: {failed_samples} ({failed_samples/total_samples*100:.1f}%)")
            print(f"Average quality score: {avg_quality:.3f}")
            print(f"Quality distribution:")
            print(f"  - Excellent (≥0.9): {excellent_samples} ({excellent_samples/total_samples*100:.1f}%)")
            print(f"  - Good (0.8-0.9): {good_samples} ({good_samples/total_samples*100:.1f}%)")
            print(f"  - Fair (0.6-0.8): {fair_samples} ({fair_samples/total_samples*100:.1f}%)")
            print(f"  - Failed gates: {failed_samples} ({failed_samples/total_samples*100:.1f}%)")
            print(f"Report saved to: {report_path}")
            print("="*50)
            
        except Exception as e:
            print(f"Warning: Failed to generate quality report: {e}")

    def save_calibration_data(self, path1):
        """保存校准数据到JSONL文件"""
        try:
            data_save_path = path1 + 'train_data.jsonl'
            os.makedirs(os.path.dirname(data_save_path), exist_ok=True)
            
            with jsonlines.open(data_save_path, mode='w') as writer:
                for json_dict in self.data_list:
                    # 创建副本并确保所有numpy数组转换为列表
                    safe_dict = {}
                    for key, value in json_dict.items():
                        if isinstance(value, np.ndarray):
                            safe_dict[key] = value.tolist()
                        elif isinstance(value, (list, tuple)):
                            # 检查列表中是否有numpy数组
                            safe_dict[key] = [item.tolist() if isinstance(item, np.ndarray) else item for item in value]
                        else:
                            safe_dict[key] = value
                    writer.write(safe_dict)
            
            print(f"Calibration data saved to {data_save_path}")
            
        except Exception as e:
            print(f"Warning: Failed to save calibration data: {e}")

    def draw_dynamic_calibration_point(self, img, point, base_radius, animation_phase, elapsed_time, gaze_stability, explosion_time, data_quality=0.0):
        """绘制动态校准点，包含动画效果"""
        # 计算动画缩放因子
        scale_factor = 1.0 + 0.2 * math.sin(elapsed_time * 2)  # 使用elapsed_time来控制动画
        radius = int(base_radius * scale_factor)
        
        # 计算颜色
        base_color = self.calculate_quality_color(data_quality)
        # 添加呼吸效果
        brightness_factor = 0.7 + 0.3 * math.sin(elapsed_time * 2)  # 使用elapsed_time来控制呼吸效果
        color = self.adjust_color_brightness(base_color, brightness_factor)
        
        # 绘制外圈
        cv2.circle(img, point, radius + 2, (0, 0, 0), 2)  # 黑色边框
        cv2.circle(img, point, radius, color, -1)  # 填充圆
        
        # 绘制内圈（动态大小）
        inner_radius = int(radius * 0.6)
        inner_color = self.adjust_color_brightness(color, 1.2)  # 内圈更亮
        cv2.circle(img, point, inner_radius, inner_color, -1)
        
        # 绘制中心点
        center_radius = int(radius * 0.3)
        center_color = self.adjust_color_brightness(color, 1.5)  # 中心点最亮
        cv2.circle(img, point, center_radius, center_color, -1)
        
        # 如果正在爆炸动画
        if explosion_time > 0:
            self.draw_explosion_effect(img, point, radius, explosion_time, color)
        
        # 添加光晕效果
        glow_radius = int(radius * 1.5)
        glow_color = self.adjust_color_brightness(color, 0.5)  # 光晕更暗
        cv2.circle(img, point, glow_radius, glow_color, 1)
        
        # 添加动态十字线
        line_length = int(radius * 0.8)
        line_thickness = 2
        # 水平线
        cv2.line(img, 
                (point[0] - line_length, point[1]),
                (point[0] + line_length, point[1]),
                color, line_thickness)
        # 垂直线
        cv2.line(img,
                (point[0], point[1] - line_length),
                (point[0], point[1] + line_length),
                color, line_thickness)
        
        # 添加动态旋转效果
        rotation_angle = elapsed_time * 180  # 使用elapsed_time来控制旋转
        for i in range(4):
            angle = rotation_angle + i * 90
            rad = math.radians(angle)
            end_x = int(point[0] + radius * 1.2 * math.cos(rad))
            end_y = int(point[1] + radius * 1.2 * math.sin(rad))
            cv2.line(img, point, (end_x, end_y), color, 1)

    def calculate_quality_color(self, quality):
        """计算基于质量的平滑渐变颜色 (BGR格式)"""
        # 确保质量值在0-1范围内
        quality = max(0.0, min(1.0, quality))
        
        # 定义颜色关键点 (BGR格式)
        # 红色 -> 橙色 -> 黄色 -> 浅绿 -> 绿色
        color_points = [
            (0, 0, 255),      # 红色 (quality = 0.0)
            (0, 69, 255),     # 橙红 (quality = 0.25)
            (0, 165, 255),    # 橙色 (quality = 0.5)
            (0, 255, 255),    # 黄色 (quality = 0.7)
            (0, 255, 128),    # 黄绿 (quality = 0.85)
            (0, 255, 0),      # 绿色 (quality = 1.0)
        ]
        
        # 对应的质量值
        quality_thresholds = [0.0, 0.25, 0.5, 0.7, 0.85, 1.0]
        
        # 找到当前质量值所在的区间
        for i in range(len(quality_thresholds) - 1):
            if quality <= quality_thresholds[i + 1]:
                # 在区间 [i, i+1] 内进行插值
                t = (quality - quality_thresholds[i]) / (quality_thresholds[i + 1] - quality_thresholds[i])
                color = self.interpolate_colors(color_points[i], color_points[i + 1], t)
                return color
        
        # 如果超出范围，返回最后一个颜色
        return color_points[-1]

    def interpolate_colors(self, color1, color2, t):
        """在两个颜色之间进行插值"""
        t = max(0.0, min(1.0, t))  # 确保t在0-1范围内
        
        b = int(color1[0] * (1 - t) + color2[0] * t)
        g = int(color1[1] * (1 - t) + color2[1] * t)
        r = int(color1[2] * (1 - t) + color2[2] * t)
        
        return (b, g, r)

    def adjust_color_brightness(self, color, factor):
        """调整颜色亮度"""
        factor = max(0.0, min(2.0, factor))  # 限制亮度因子在合理范围内
        
        b = int(min(255, color[0] * factor))
        g = int(min(255, color[1] * factor))
        r = int(min(255, color[2] * factor))
        
        return (b, g, r)

    def adjust_color_saturation(self, color, factor):
        """调整颜色饱和度"""
        # 转换为灰度值
        gray = int(0.299 * color[2] + 0.587 * color[1] + 0.114 * color[0])
        
        # 向灰度值或原色值插值
        if factor > 1.0:
            # 增强饱和度
            factor = min(2.0, factor)
            b = int(min(255, gray + (color[0] - gray) * factor))
            g = int(min(255, gray + (color[1] - gray) * factor))
            r = int(min(255, gray + (color[2] - gray) * factor))
        else:
            # 降低饱和度
            factor = max(0.0, factor)
            b = int(gray + (color[0] - gray) * factor)
            g = int(gray + (color[1] - gray) * factor)
            r = int(gray + (color[2] - gray) * factor)
        
        return (b, g, r)

    def draw_explosion_effect(self, img, point, base_radius, explosion_time, color=(0, 255, 255)):
        """绘制爆炸效果（可自定义颜色）"""
        x, y = point
        num_particles = 12
        max_radius = base_radius * 3
        
        for i in range(num_particles):
            angle = (i / num_particles) * 2 * math.pi
            distance = explosion_time * 100  # 粒子移动速度
            
            if distance < max_radius:
                particle_x = int(x + math.cos(angle) * distance)
                particle_y = int(y + math.sin(angle) * distance)
                
                # 粒子大小随时间衰减
                particle_size = max(1, int(base_radius * 0.3 * (1 - explosion_time * 2)))
                alpha = max(0, 1 - explosion_time * 2)
                particle_color = (
                    int(color[0] * alpha),
                    int(color[1] * alpha), 
                    int(color[2] * alpha)
                )
                
                cv2.circle(img, (particle_x, particle_y), particle_size, particle_color, -1)
        
        # 中心闪光效果
        if explosion_time < 0.2:
            flash_radius = int(base_radius * (1 + explosion_time * 3))
            flash_alpha = 1 - explosion_time * 5
            flash_color = (
                int(color[0] * flash_alpha),
                int(color[1] * flash_alpha), 
                int(color[2] * flash_alpha)
            )
            cv2.circle(img, (x, y), flash_radius, flash_color, -1)

    def draw_calibration_progress_simple(self, img, point_idx, total_points, photos_taken, total_photos, gaze_stability, data_quality=0.0, attempted_photos=0):
        """绘制校准进度信息（简化版，不包含右下角图例）"""
        screen_width, screen_height = self.screen_size
        
        # 绘制点进度
        progress_text = f"Point {point_idx + 1} of {total_points}"
        cv2.putText(img, progress_text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        # 绘制数据收集进度
        data_progress = f"Valid Photos: {photos_taken}/{total_photos}"
        cv2.putText(img, data_progress, (50, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        
        # 绘制尝试次数
        if attempted_photos > 0:
            attempt_text = f"Attempts: {attempted_photos}"
            cv2.putText(img, attempt_text, (50, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
        
        # 绘制注视稳定性指示器
        stability_text = f"Focus: {int(gaze_stability * 100)}%"
        # 使用平滑的颜色渐变
        stability_color = self.calculate_quality_color(gaze_stability)
        cv2.putText(img, stability_text, (50, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.8, stability_color, 2)
        
        # 绘制数据质量指示器
        quality_text = f"Quality: {int(data_quality * 100)}%"
        # 使用平滑的质量颜色
        quality_color = self.calculate_quality_color(data_quality)
        cv2.putText(img, quality_text, (50, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.8, quality_color, 2)
        
        # 绘制整体进度条（放在左上角，不会挡住校准点）
        bar_width = 300
        bar_height = 20
        bar_x = 50
        bar_y = 300
        
        overall_progress = (point_idx + photos_taken / total_photos) / total_points
        
        # 背景
        cv2.rectangle(img, (bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height), (100, 100, 100), -1)
        
        # 进度条
        progress_width = int(bar_width * overall_progress)
        if progress_width > 0:
            # 根据整体进度计算颜色
            progress_color = self.calculate_quality_color(overall_progress)
            cv2.rectangle(img, (bar_x, bar_y), (bar_x + progress_width, bar_y + bar_height), progress_color, -1)
        
        # 边框
        cv2.rectangle(img, (bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height), (255, 255, 255), 2)
        
        # 进度百分比
        progress_percent = f"{int(overall_progress * 100)}%"
        cv2.putText(img, progress_percent, (bar_x + bar_width + 10, bar_y + 15), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    def collect_historical_calibration_data(self, base_calibration_dir="calibration"):
        """收集所有历史校准数据的路径"""
        historical_jsonl_paths = []
        
        try:
            if not os.path.exists(base_calibration_dir):
                print(f"Calibration directory {base_calibration_dir} does not exist")
                return historical_jsonl_paths
            
            # 遍历校准目录下的所有日期文件夹
            for date_folder in os.listdir(base_calibration_dir):
                date_path = os.path.join(base_calibration_dir, date_folder)
                if os.path.isdir(date_path):
                    # 查找该日期文件夹下的train_data.jsonl文件
                    jsonl_file = os.path.join(date_path, "train_data.jsonl")
                    if os.path.exists(jsonl_file):
                        # 验证文件不为空且格式正确
                        try:
                            # 尝试读取文件并检查是否有数据
                            with jsonlines.open(jsonl_file, 'r') as reader:
                                data_lines = list(reader)
                                if data_lines:  # 如果有数据行
                                    historical_jsonl_paths.append(jsonl_file)
                                    print(f"Found calibration data: {jsonl_file} ({len(data_lines)} samples)")
                                else:
                                    print(f"Warning: Empty jsonl file {jsonl_file}")
                        except Exception as e:
                            print(f"Warning: Invalid jsonl file {jsonl_file}: {e}")
            
            print(f"Found {len(historical_jsonl_paths)} historical calibration datasets")
            return historical_jsonl_paths
            
        except Exception as e:
            print(f"Error collecting historical data: {e}")
            return historical_jsonl_paths

    def train_with_accumulated_data(self, current_calibration_path=None, max_datasets=10):
        """使用累积的校准数据进行训练"""
        historical_paths = self.collect_historical_calibration_data()

        if current_calibration_path:
            current_jsonl = os.path.join(current_calibration_path, "train_data.jsonl")
            if os.path.exists(current_jsonl):
                historical_paths.append(current_jsonl)

        if not historical_paths:
            print("No historical calibration data found, training with current data only")
            if hasattr(self, 'data_list') and self.data_list:
                self.train_regression(reset=True)
                return True
            print("No current data available either")
            return False

        historical_paths.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        if len(historical_paths) > max_datasets:
            historical_paths = historical_paths[:max_datasets]
            print(f"Using most recent {max_datasets} datasets for training")

        all_data = []
        total_samples = 0
        for jsonl_path in historical_paths:
            with jsonlines.open(jsonl_path, 'r') as reader:
                dataset_data = list(reader)
            all_data.extend(dataset_data)
            total_samples += len(dataset_data)
            print(f"Loaded {len(dataset_data)} samples from {os.path.basename(os.path.dirname(jsonl_path))}")

        if not all_data:
            print("No valid data loaded from historical files")
            return False

        print(f"Total accumulated samples: {total_samples}")
        print("Training with accumulated data...")
        self.train_regression(data_list=all_data, reset=True)

        if self.is_model_fitted():
            print("Accumulated training completed successfully!")
            return True
        print("Accumulated training failed")
        return False

    def train_incremental(self, current_calibration_path=None, learning_rate_decay=0.9):
        """增量训练：在现有模型基础上用新数据进行更新"""
        try:
            # 检查是否已有训练好的模型
            if not self.is_model_fitted():
                print("No existing model found, performing full training instead")
                return self.train_with_accumulated_data(current_calibration_path)
            
            # 加载当前校准数据
            if current_calibration_path:
                current_jsonl = os.path.join(current_calibration_path, "train_data.jsonl")
                if os.path.exists(current_jsonl):
                    with jsonlines.open(current_jsonl, 'r') as reader:
                        new_data = list(reader)
                    
                    if new_data:
                        print(f"Performing incremental training with {len(new_data)} new samples")
                        
                        # 对于支持增量学习的模型进行特殊处理
                        if hasattr(self.regression_model, 'partial_fit'):
                            # 支持增量学习的模型（如SGDRegressor）
                            X, y = self.data_dict_list_preparation_for_training_and_evaluation(new_data, include_labels=True)
                            self.regression_model.partial_fit(X, y)
                            print("Incremental training completed")
                            return True
                        else:
                            # 不支持增量学习的模型，回退到累积训练
                            print("Model doesn't support incremental learning, using accumulated training")
                            return self.train_with_accumulated_data(current_calibration_path)
                    else:
                        print("No new data to train with")
                        return True
                else:
                    print(f"No current calibration data found at {current_jsonl}")
                    return True
            else:
                print("No current calibration path provided")
                return True
                
        except Exception as e:
            print(f"Error in incremental training: {e}")
            return False



class BindKeys(IntegratedRegressionMediaPipeline):
    """
    process mediapipe results to face actions, head actions
    record the time of last action start, number of actions, which is important to decide some state
    """
    from .utils import StateRecordDict
    def __init__(self, head_angles_center=None, head_angles_scale=None, 
                 expression_evaluator_config=None,
                 **kwargs):
        super().__init__(**kwargs)
        self.features = None
        self.face_observation_valid = False
        self.keys_dict = StateRecordDict()  # only for bool value
        self.head_dict = StateRecordDict()  # only for bool value
        self.mouse_dict = None
        self.expression_evaluator = ExpressionEvaluator(expression_evaluator_config)
        self.expression_evaluator_config = expression_evaluator_config
        if head_angles_center is None:
            self.head_angles_center = {
                'yaw': 0,
                'pitch': 0,
                'roll': 0,
            }
        else:
            self.head_angles_center = head_angles_center
        if head_angles_scale is None:
            self.head_angles_scale = {
                'yaw': 8,
                'pitch': 8,
                'roll': 8,
            }
        else:
            self.head_angles_scale = head_angles_scale

    def call_before_while_loop(self):
        # 记录keys现在是否被按下，初始状态是都没有被按下，在对keys进行操作时，必须也对这个状态字典进行修改，只在状态会改变的时候进行操作
        pass

    def call_after_each_eval_loop(self):
        super().call_after_each_eval_loop()
        self.bind_keys()
        self.head_pose()
        self.move_mouse()
        # t2=time.time()
        # print(t2-t1)
        # 这里的计算的确不占什么时间

    def head_pose(self):
        # print(self.mp_result.facial_transformation_matrixes)
        try:
            head_angles = self.orig_head_angles.tolist()
        except Exception as e:
            head_angles = [0, 0, 0]

        # pitch: 抬头 -8，低头 8
        # yaw: 左转 -10， 右转 10
        # roll: 左低头 -10 右低头 10

        pitch, yaw, roll = head_angles[0], head_angles[1], head_angles[2]
        pitch = pitch - self.head_angles_center['pitch']
        yaw = yaw - self.head_angles_center['yaw']
        roll = roll - self.head_angles_center['roll']
        
        self.head_angles = {
            'pitch': pitch,
            'yaw': yaw,
            'roll': roll,
        }
        head_dict = {
            'head_down': pitch < -self.head_angles_scale['pitch'],  # 其实这个低头确实没有错，但是后面屏幕的y轴是反的，之后移动时需要反转。
            'head_up': pitch > self.head_angles_scale['pitch'],
            'head_left': yaw > self.head_angles_scale['yaw'],
            'head_right': yaw < -self.head_angles_scale['yaw'],
            'head_roll_left': roll < -self.head_angles_scale['roll'],
            'head_roll_right': roll > self.head_angles_scale['roll'],
        }
        self.head_dict.update_dict(head_dict)

    def move_mouse(self):
        predicted_position = self.predicted_position
        # print(predicted_position)
        if predicted_position is not None:
            x, y = predicted_position
            mx, my = desktop.get_pointer_position()
            rel_x = x - mx
            rel_y = y - my
            self.mouse_dict = {
                'rel_x': rel_x,
                'rel_y': rel_y,
                'x': x,
                'y': y,
                'mx': mx,
                'my': my,
            }

    def bind_keys(self):
        face_blendshapes = self.mp_result.face_blendshapes
        self.face_observation_valid = len(face_blendshapes) == 1
        if self.face_observation_valid:
            face_blendshapes = face_blendshapes[0]
            face_blendshapes_names = [face_blendshapes_category.category_name for face_blendshapes_category in
                                      face_blendshapes]
            face_blendshapes_scores = [face_blendshapes_category.score for face_blendshapes_category in
                                       face_blendshapes]
            f = dict(zip(face_blendshapes_names, face_blendshapes_scores))
            self.features = f
            # print(f'features:{f}')
            ### 这个是用来控制是否绑定键盘的
            # 如果key_control是None，就绑定键盘
            # 如果key_control是False，就不绑定键盘
            # 如果key_control是True，就绑定键盘
            key_control=True
            if not hasattr(self,'key_control'):
                key_control=True 
            else:
                key_control=self.key_control
            if not key_control:
                return
            # keys_dict = {
            #     'numlock': f['jawOpen'] > 0.4 and f['jawLeft'] < 0.1 and f['jawRight'] < 0.1,
            #     'num0': f['mouthRollLower'] > 0.45 and f['mouthRollUpper'] > 0.45,
            #     'num1': 0.25<f['mouthSmileLeft'] < 0.45 and f['mouthSmileLeft'] - f['mouthSmileRight'] > 0.15,
            #     'num2': f['mouthSmileLeft'] > 0.45 and f['mouthSmileRight'] > 0.45 and abs(
            #         f['mouthSmileLeft'] - f['mouthSmileRight']) < 0.2,
            #     'num3': 0.25<f['mouthSmileRight'] < 0.45 and f['mouthSmileRight'] - f['mouthSmileLeft'] > 0.15,
            #     'num4': f['mouthLeft'] > 0.2 and f['jawOpen'] < 0.05 and
            #             f['mouthSmileLeft'] < 0.2 and f['mouthSmileRight'] < 0.2,
            #     'num5': f['mouthPressLeft'] > 0.4 and f['mouthPressRight'] > 0.4,
            #     'num6': f['mouthRight'] > 0.2 and f['jawOpen'] < 0.05 and
            #             f['mouthSmileLeft'] < 0.2 and f['mouthSmileRight'] < 0.2,
            #     'num7': f['mouthUpperUpLeft'] > 0.5 and f['mouthUpperUpRight'] > 0.5 and
            #             f['mouthLowerDownLeft'] > 0.3 and f['mouthLowerDownRight'] > 0.3,
            #     'num8': f['browInnerUp'] > 0.8,
            #     'num9': f['mouthFunnel'] > 0.4,
            #     'right_click': f['jawLeft'] > 0.3,
            #     'mid_click': f['jawRight'] > 0.3,
            #     'left_click': f['mouthPucker'] > 0.97 and f['mouthFunnel'] < 0.2,
            #     'extra': f['eyeBlinkLeft'] > 0.6 and f['eyeBlinkRight'] < 0.25,
            # }
            # # 附加条件
            # if keys_dict['num7']:
            #     keys_dict['num2'] = False
            # for k, v in keys_dict.items():
            #     if k != 'left_click' and v:
            #         keys_dict['left_click'] = False
            #         break

            # this will record everything we need for every key
            keys_dict = self.expression_evaluator.evaluate_all(f)
            
            self.keys_dict.update_dict(keys_dict)
            # print(f'keys_dict:{keys_dict}')
            # print(f'num2:{keys_dict["num2"]}')


class RealAction(BindKeys):
    def __init__(self,show_gaze=True, mouse_control=False,key_control=False,
                 scroll_coef=2, sys_mode='type', 
                 gaze_config=None, mouse_control_config=None,
                 wheel_config=None,
                 configuration=None,
                 head_angles_center=None, head_angles_scale=None,
                 expression_evaluator_config=None,
                 robot_action_config=None,
                 robot_action_output_config=None,
                 robot_wheel_config=None,
                 action_platform=None,
                 **kwargs):
        platform_name = sys.platform if action_platform is None else action_platform
        if platform_name == "win32":
            self.action_output = "desktop"
        elif platform_name.startswith("linux"):
            self.action_output = "robot_terminal"
        else:
            raise RuntimeError(
                f"unsupported action platform: {platform_name!r}"
            )
        if gaze_config is None:
            raise ValueError("gaze_config is required")

        validated_robot_wheel_config = None
        if self.action_output == "robot_terminal":
            if robot_action_config is None:
                raise ValueError("robot_action_config is required")
            if robot_action_output_config is None:
                raise ValueError("robot_action_output_config is required")
            if robot_wheel_config is None:
                raise ValueError("robot_wheel_config.layout is required")
            if not isinstance(robot_wheel_config, Mapping):
                raise TypeError("robot_wheel_config must be a mapping")
            allowed_wheel_fields = (
                "layout",
                "selection",
                "yaw_threshold_degrees",
                "pitch_threshold_degrees",
            )
            for field_name in robot_wheel_config:
                if field_name not in allowed_wheel_fields:
                    raise ValueError(
                        f"robot_wheel_config.{field_name} is not allowed"
                    )
            for field_name in allowed_wheel_fields:
                if field_name not in robot_wheel_config:
                    raise ValueError(
                        f"robot_wheel_config.{field_name} is required"
                    )
            layout = robot_wheel_config["layout"]
            if not isinstance(layout, str):
                raise TypeError("robot_wheel_config.layout must be a string")
            if layout != "fullscreen_cardinal":
                raise ValueError(
                    "robot_wheel_config.layout must equal "
                    "'fullscreen_cardinal'"
                )
            selection = robot_wheel_config["selection"]
            if not isinstance(selection, str):
                raise TypeError(
                    "robot_wheel_config.selection must be a string"
                )
            if selection != "head_pose":
                raise ValueError(
                    "robot_wheel_config.selection must equal 'head_pose'"
                )
            for field_name in (
                "yaw_threshold_degrees",
                "pitch_threshold_degrees",
            ):
                value = robot_wheel_config[field_name]
                if isinstance(value, bool) or not isinstance(value, Real):
                    raise TypeError(
                        f"robot_wheel_config.{field_name} must be a number"
                    )
                if not 0 < value <= 45:
                    raise ValueError(
                        f"robot_wheel_config.{field_name} must be in "
                        "the interval (0, 45]"
                    )
            validated_robot_wheel_config = copy.deepcopy(robot_wheel_config)

        super().__init__(
            head_angles_center=head_angles_center, 
            head_angles_scale=head_angles_scale, 
            expression_evaluator_config=expression_evaluator_config,
            **kwargs)
        self.mouse_control = mouse_control
        self.key_control = key_control
        self.head_angles_center = head_angles_center
        self.head_angles_scale = head_angles_scale
        
        self.show_gaze = show_gaze
        self.gaze_config = gaze_config
        self.gaze_overlay = None
        self.scroll_coef = scroll_coef

        controller_config = dict(mouse_control_config)
        if self.action_output == "robot_terminal":
            self.uses_desktop_input = False
            for field_name in (
                "desktop_pointer_control",
                "select_wheel_using_head",
            ):
                if (
                    field_name in controller_config
                    and controller_config[field_name] is not False
                ):
                    raise ValueError(
                        f"robot_terminal requires {field_name}=False"
                    )
                controller_config[field_name] = False

        from .eye_gaze_mouse_control import GazeMouseController
        self.gaze_mouse_controller = GazeMouseController(
            observer=self,
            screen_width=self.screen_size[0],
            screen_height=self.screen_size[1],
            **controller_config
        )
        # from .expression_keyboard_control import ExpressionKeyboardController
        # self.keyboard_controller = ExpressionKeyboardController(self)
        if self.action_output == "robot_terminal":
            self.robot_action_config = validate_robot_action_config(
                robot_action_config
            )
            from .sonic_action_client import (
                SonicActionClient,
                validate_robot_action_output_config,
            )

            self.robot_action_output_config = (
                validate_robot_action_output_config(
                    robot_action_output_config
                )
            )
            if self.robot_action_output_config["type"] == "sonic_ipc":
                self.sonic_action_client = SonicActionClient(
                    endpoint=self.robot_action_output_config["endpoint"],
                    timeout_ms=self.robot_action_output_config["timeout_ms"],
                )
            else:
                self.sonic_action_client = None
            self.robot_wheel_config = validated_robot_wheel_config
            self.configuration = {"robot": {}}
            self.sys_mode = "robot"
        else:
            if configuration is None:
                raise ValueError("configuration is required")
            self.configuration = self.get_configuration(configuration)
            self.sys_mode = sys_mode
        self.sys_mode_list = list(self.configuration.keys())
        self.wheel_categories = None
        self.key_keeps_wheel_opening = None
        self.is_key_down = False  # 一些操作需要同时按下多个键，这就需要一个状态来记录是否用keyDown来按键，一个列表来记录按下的键。
        self.down_keys_list = []  # 当is_key_down==True,这里就会开始加入接下来被按下的键。
        # 当is_key_down==False时，这里就会逐个反向释放key，并且清空这个列表。
        self.op_xy = (None, None)
        self.op_xy_generation = 0
        self.published_op_xy_generation = 0
        self.robot_wheel_observation_generation = 0
        self.robot_wheel_observation = None
        if self.action_output == "robot_terminal":
            wheel_runtime_config = self.robot_wheel_config
        else:
            wheel_runtime_config = wheel_config
        self.wheel = ObserverWithSectorWheel(self, **wheel_runtime_config)
        self.action_queue = queue.Queue()
        self.lock_eye_controlled_mouse_move_until_time = time.time()
        self.lock_eye_controlled_mouse_move_with_head_until_time = time.time()

        self.is_mouse_visible = False
        self.wheel_layout_type = 'circle'

        # 添加滚轮节流相关变量
        self.last_scroll_time = 0
        self.scroll_throttle_interval = 0.2  # 0.2秒间隔

    def next_op_xy_generation(self):
        self.op_xy_generation += 1
        return self.op_xy_generation

    def publish_op_xy(self, generation, x, y):
        self.op_xy = (x, y)
        self.published_op_xy_generation = generation

    def move_mouse(self):
        if self.action_output == "robot_terminal":
            self.mouse_dict = None
            return
        super().move_mouse()

    def start_gaze_display(self):
        """启动凝视点显示。"""
        if self.gaze_overlay is not None:
            raise RuntimeError("gaze display is already started")
        self.show_gaze = True

        from .gaze_overlay import GazeOverlay
        overlay = GazeOverlay(**self.gaze_config)
        overlay.start()
        self.gaze_overlay = overlay


    def stop_gaze_display(self):
        """停止凝视点显示"""
        self.show_gaze = False
        self._stop_gaze_display()

    def _stop_gaze_display(self):
        overlay = self.gaze_overlay
        if overlay is None:
            return
        overlay.stop()
        self.gaze_overlay = None


    def set_show_gaze(self, show):
        """设置是否显示凝视点"""
        if show != self.show_gaze:
            self.show_gaze = show
            if show:
                self.start_gaze_display()
            else:
                self.stop_gaze_display()

    def update_gaze_config(self, new_config):
        """更新凝视点配置"""
        self.gaze_config.update(new_config)
        if self.show_gaze:
            # 重启凝视点显示以应用新配置
            self.stop_gaze_display()
            self.start_gaze_display()

    def get_configuration(self, configuration):
        if configuration is None:
            configuration = {
                'game': {
                    'numlock': {'wheel': ['game', 'type', 'game_cs'], },
                    'num0': {'wheel': ['e']},
                    'num1': {'wheel': ['z', 'x', 'c']},
                    'num2': {'wheel': ['shift']},
                    'num3': {'wheel': ['v']},
                    'num4': {'wheel': ['1', '2', '3', '4']},
                    'num5': {'wheel': ['g']},
                    'num6': {'wheel': ['q', 'r', 'f', 't']},
                    'num7': {'wheel': ['esc']},
                    'num8': {'wheel': ['space']},
                    'num9': {'wheel': ['ctrl']},
                    'left_click': {'wheel': ['mouse_left'], 'induce': {'lock_mouse_move': {'duration': 1}}},
                    'mid_click': {'wheel': ['mouse_middle']},
                    'right_click': {'wheel': ['mouse_right'], },
                    'extra': {'wheel': [None]},
                    'head_up': {'wheel': ['s']},
                    # take move with head rather than eye for 1 sec, if no head movement in 1s, change back to eye
                    'head_down': {'wheel': ['w']},
                    'head_left': {'wheel': ['a']},
                    'head_right': {'wheel': ['d']},
                    'head_roll_left': {'wheel': ['scroll_up'], },
                    'head_roll_right': {'wheel': ['scroll_down'], },
                },
                'game_cs': {
                    'numlock': {'wheel': ['game', 'type', 'game_cs'], },
                    'num0': {'wheel': ['e']},
                    'num1': {'wheel': ['z', 'x', 'c']},
                    'num2': {'wheel': ['space']},
                    'num3': {'wheel': ['v']},
                    'num4': {'wheel': ['1', '2', '3', '4']},
                    'num5': {'wheel': ['g']},
                    'num6': {'wheel': ['q', 'r', 'f', 't']},
                    'num7': {'wheel': ['esc']},
                    'num8': {'wheel': ['shift']},
                    'num9': {'wheel': ['ctrl']},
                    'left_click': {'wheel': ['mouse_left'], 'induce': {'lock_mouse_move': {'duration': 0.0}}},
                    'mid_click': {'wheel': ['mouse_middle']},
                    'right_click': {'wheel': ['mouse_right'], },
                    'extra': {'wheel': [None]},
                    'head_up': {'wheel': ['s']},
                    # take move with head rather than eye for 1 sec, if no head movement in 1s, change back to eye
                    'head_down': {'wheel': ['w']},
                    'head_left': {'wheel': ['a']},
                    'head_right': {'wheel': ['d']},
                    'head_roll_left': {'wheel': ['scroll_up'], },
                    'head_roll_right': {'wheel': ['scroll_down'], },
                },
                'type': {
                    'numlock': {'wheel': ['game', 'type', 'game_cs'], },
                    'num0': {'wheel': ['keydown', 'keyup']},
                    'num1': {'wheel': ['backspace']},
                    'num2': {'wheel': ['shift', 'ctrl', 'caps', 'tab', 'alt', 'esc', 'fn', 'super']},
                    # 这里的super是win
                    'num3': {'wheel': ['ctrl+c', 'ctrl+v', 'ctrl+q', 'ctrl+a', 'ctrl+alt']},
                    'num4': {'wheel': [chr(i) for i in range(97, 97 + 26, 1)] + ['backspace', ' ', 'enter'],
                             'layout_type': "square"},
                    'num5': {'wheel': [None]},
                    'num6': {'wheel': [str(i) for i in range(10)] + ['`', '-', '=', '[', ']', '\\', ';', '\'', ',', '.',
                                                                     '/'], 'layout_type': "square"},
                    'num7': {'wheel': ['esc']},
                    'num8': {'wheel': ['space']},
                    'num9': {'wheel': [f'F{i + 1}' for i in range(12)]},
                    'left_click': {'wheel': ['mouse_left'], 'induce': {'lock_mouse_move': {'duration': 1}}},
                    'mid_click': {'wheel': ['mouse_middle']},
                    'right_click': {'wheel': ['mouse_right'], },
                    'extra': {'wheel': [None]},
                    # take move with head rather than eye for 1 sec, if no head movement in 1s, change back to eye
                    # 'head_up': {'wheel': ['w']},
                    # 'head_down': {'wheel': ['s']},
                    # 'head_left': {'wheel': ['a']},
                    # 'head_right': {'wheel': ['d']},
                    'head_roll_left': {'wheel': ['scroll_up'], },
                    'head_roll_right': {'wheel': ['scroll_down'], },
                }
            }
        return configuration

    def call_before_while_loop(self):
        with self._lifecycle_lock:
            super().call_before_while_loop()
            if self.quit:
                raise RuntimeError("pipeline has been shut down")
            self.wheel.start()
            if self.show_gaze:
                self.start_gaze_display()
            self.gaze_mouse_controller.update_screen_size(
                self.screen_size[0], self.screen_size[1]
            )
            if self.action_output == "desktop":
                self.gaze_mouse_controller.start()

    def _discard_actions(self):
        while True:
            try:
                self.action_queue.get_nowait()
            except queue.Empty:
                return

    def _drain_actions(self):
        while True:
            try:
                action = self.action_queue.get_nowait()
            except queue.Empty:
                return
            self._execute_action(action)

    def _finish_run(self):
        with self._lifecycle_lock:
            if self.quit:
                return
            self.wheel.stop()
            self._drain_actions()
            self._stop_gaze_display()
            super()._finish_run()

    def set_mouse_control(self,mouse_control):
        self.mouse_control = mouse_control

    def loop_mouse(self):
        old_x, old_y = None, None
        while 1:
            t0 = time.time()
            time.sleep(0.1)
            self.is_mouse_visible = desktop.is_cursor_visible()
            # print(f'visible:{self.is_mouse_visible}')
            # 鼠标位移操作
            # 这个需要放在action queue之前，因为后面有个continue的操作，会跳过鼠标
            # 鼠标位移还是不能放这里，因为这个loop
            # if time.time() > self.lock_eye_controlled_mouse_move_until_time:

            if self.mouse_dict is None:
                pass
            else:
                # print(f'mouse_dict:{self.mouse_dict}')
                if time.time() > self.lock_eye_controlled_mouse_move_until_time:
                    # if time has passed by lock time
                    # if np.abs(self.mouse_dict['rel_x']) > 5 or np.abs(self.mouse_dict['rel_y']) > 5:
                    # rel_x,rel_y=self.mouse_dict['x']-self.mid_point[0],self.mouse_dict['y']-self.mid_point[1]
                    x, y = self.mouse_dict['x'], self.mouse_dict['y']
                    x = np.clip(a=x, a_min=0, a_max=self.screen_size[0])
                    y = np.clip(a=y, a_min=0, a_max=self.screen_size[1])
                    if self.is_mouse_visible:
                        # 看得到鼠标就是正常模式
                        # pg.moveTo(x=int(x),y=int(y))
                        # 要加一个用头来移动鼠标的方式，因为眼睛瞄不准，用头移动鼠标比较方便。
                        # 用头移动鼠标的条件是有鼠标图标，只要这个移动了，眼球就脱离控制2s。
                        # 先想一下之前的头的控制
                        # 现在我想试试用头来控制选择，感觉会更流畅。只有wheel打开的时候才切到头
                        if self.wheel.is_hidden:
                            print(f'wheel is hidden,mode:{self.sys_mode}')
                            # wheel被隐藏时
                            y_dir = int(self.head_dict.state_dict['head_down']['v']) - int(
                                self.head_dict.state_dict['head_up']['v'])
                            x_dir = int(self.head_dict.state_dict['head_right']['v']) - int(
                                self.head_dict.state_dict['head_left']['v'])
                            rel = 10
                            rel_y = rel * y_dir
                            rel_x = rel * x_dir
                            # print(f'rel_x:{rel_x},rel_y:{rel_y}')
                            if rel_y != 0 or rel_x != 0:
                                # mx=self.mouse_dict['mx']
                                # my=self.mouse_dict['my']
                                mx, my = desktop.get_pointer_position()
                                x = rel_x + mx
                                y = rel_y + my
                                x = np.clip(a=x, a_min=0, a_max=self.screen_size[0])
                                y = np.clip(a=y, a_min=0, a_max=self.screen_size[1])
                                desktop.move_pointer(
                                    int(x), int(y), relative=False
                                )
                                # pg.moveRel(xOffset=mx+rel_x,yOffset=rel_y)
                                self.lock_eye_controlled_mouse_move_with_head_until_time = time.time() + 2
                            else:
                                if time.time() > self.lock_eye_controlled_mouse_move_with_head_until_time:
                                    if old_x != x or old_y != y:
                                        desktop.move_pointer(
                                            int(x), int(y), relative=False
                                        )
                                    old_x, old_y = x, y
                        else:
                            # 轮盘显示时用头部角度控制
                            print(f'wheel is visible,mode:{self.sys_mode}')
                            pitch = self.head_angles['pitch']
                            yaw = self.head_angles['yaw']
                            scale = 100
                            y = self.mid_point[1] + scale * pitch
                            x = self.mid_point[0] - scale * yaw
                            x = np.clip(a=x, a_min=0, a_max=self.screen_size[0])
                            y = np.clip(a=y, a_min=0, a_max=self.screen_size[1])
                            if old_x != x or old_y != y:
                                desktop.move_pointer(
                                    int(x), int(y), relative=False
                                )
                            old_x, old_y = x, y

                    else:
                        # 看不到鼠标就是第一视角模式
                        print(f'mouse is not visible,mode:{self.sys_mode}')
                        t2 = time.time()
                        mx, my = self.mid_point[0], self.mid_point[1]
                        edge_length = 1000
                        bbox_xxyy = [mx - edge_length // 2, mx + edge_length // 2,
                                     my - edge_length // 2, my + edge_length // 2]
                        bbox_xxyy = np.array(bbox_xxyy)
                        sw, sh = self.screen_size
                        screen_edge = 20
                        bbox_xxyy[:2] = np.clip(bbox_xxyy[:2], a_min=0 + screen_edge, a_max=sw - screen_edge)
                        bbox_xxyy[2:] = np.clip(bbox_xxyy[2:], a_min=0 + screen_edge, a_max=sh - screen_edge)
                        # 计算视点和边框的距离
                        rel_x = (np.sign(x - bbox_xxyy[0]) + np.sign(x - bbox_xxyy[1])) / 2 * (
                            np.min([np.abs(x - bbox_xxyy[0]), np.abs(x - bbox_xxyy[1])]))
                        rel_y = (np.sign(y - bbox_xxyy[2]) + np.sign(y - bbox_xxyy[3])) / 2 * (
                            np.min([np.abs(y - bbox_xxyy[2]), np.abs(y - bbox_xxyy[3])]))
                        rel_x = rel_x // 5
                        rel_y = rel_y // 5
                        t3 = time.time()
                        # print(f'loop mouse calc time:{t3-t2}s')
                        print(f'rel_x: {rel_x}, rel_y: {rel_y}')
                        if np.abs(rel_x) > 5 or np.abs(rel_y) > 2:
                            max_mag = 20
                            rel_x = np.clip(rel_x, -max_mag, max_mag)
                            rel_y = np.clip(rel_y, -max_mag, max_mag)
                        t4 = time.time()
                        # print(f'loop mouse thread time:{t4-t3}s')
            t1 = time.time()
            # print(f'loop mouse time:{t1-t0}')
            if self.quit:
                quit()

    def make_wheel_action(self, selected: object) -> Action | RobotAction | None:
        if self.action_output == "robot_terminal":
            if selected is None:
                emit_robot_action_cancelled(
                    reason="no_selection", source="wheel"
                )
                return None
            if not isinstance(selected, RobotAction):
                raise TypeError("Ubuntu robot wheel requires RobotAction")
            return selected
        return Action(str(selected), OpType.KEYPRESS)

    def _execute_action(self, action):
        try:
            return self._execute_action_once(action)
        except BaseException as error:
            try:
                self.wheel.stop()
            except BaseException as cleanup_error:
                error.add_note(
                    "wheel.stop after action failure failed with "
                    f"{type(cleanup_error).__name__}: {cleanup_error}"
                )
            try:
                self._discard_actions()
            except BaseException as cleanup_error:
                error.add_note(
                    "action discard after action failure failed with "
                    f"{type(cleanup_error).__name__}: {cleanup_error}"
                )
            raise

    def _execute_action_once(self, action):
        if self.action_output == "robot_terminal":
            if not isinstance(action, RobotAction):
                raise TypeError("Ubuntu robot output requires RobotAction")
            if self.sonic_action_client is not None:
                self.sonic_action_client.send(action)
            emit_robot_action(action)
            return
        if isinstance(action, RobotAction):
            raise TypeError("Windows desktop output rejects RobotAction")
        if action is None or action.keyname is None:
            return
        if getattr(action, "op_type", None) == OpType.NONE:
            return

        action_key = str(action.keyname)
        action_key = {
            "caps": "caps_lock",
            "super": "win",
        }.get(action_key, action_key)
        action.keyname = action_key
        print(f"action_key:{action_key} type:{type(action_key)}")
        if desktop.supports_key(action_key):
            action.execute()
            return

        if len(action_key) != 1 and "+" in action_key:
            pressed_keys = []
            try:
                for key in action_key.split("+"):
                    desktop.key_down(key)
                    pressed_keys.append(key)
            except BaseException as error:
                for key in reversed(pressed_keys):
                    try:
                        desktop.key_up(key)
                    except BaseException as cleanup_error:
                        error.add_note(
                            f"desktop.key_up({key!r}) failed with "
                            f"{type(cleanup_error).__name__}: "
                            f"{cleanup_error}"
                        )
                raise

            cleanup_errors = []
            for key in reversed(pressed_keys):
                try:
                    desktop.key_up(key)
                except BaseException as error:
                    cleanup_errors.append(error)
            if cleanup_errors:
                raise BaseExceptionGroup(
                    "hotkey release failed",
                    cleanup_errors,
                )
            return

        if action_key in self.sys_mode_list:
            self.sys_mode = action_key
            return

        if action_key in ("scroll_down", "scroll_up"):
            current_time = time.time()
            if (
                current_time - self.last_scroll_time
                >= self.scroll_throttle_interval
            ):
                desktop.scroll(
                    int(
                        np.sign(self.head_angles["roll"])
                        * (
                            np.abs(self.head_angles["roll"])
                            - self.head_angles_scale["roll"]
                        )
                        * self.scroll_coef
                    )
                )
                self.last_scroll_time = current_time
            return

        raise ValueError(f"unsupported action key: {action_key!r}")

    def call_after_each_eval_loop(self):
        self.wheel.raise_if_failed()
        self.gaze_mouse_controller.raise_if_failed()
        t0 = time.time()
        super().call_after_each_eval_loop()
        t1 = time.time()
        overlay = self.gaze_overlay
        if overlay is not None:
            if self.predicted_position is not None:
                overlay.update_gaze_position(
                    int(self.predicted_position[0]),
                    int(self.predicted_position[1]),
                )
            overlay.raise_if_failed()
        # now take real actions
        # call out wheel, press keys, lock
        # use different configuration of actions

        # new_categories should be locked if an intention is detected and not disappeared.

        # recall all variables we have
        # keys_dict, shared_keys_state_dict,shared_keys_time_dict,mouse_dict,head_dict
        self.decode()
        if self.action_output == "robot_terminal":
            self._publish_robot_wheel_observation()
        t2 = time.time()
        if self.action_output == "desktop" and self.mouse_dict is not None:
            self.gaze_mouse_controller.update_gaze(
                self.mouse_dict['x'], self.mouse_dict['y']
            )
        self._drain_actions()


    def _publish_robot_wheel_observation(self):
        self.robot_wheel_observation_generation += 1
        generation = self.robot_wheel_observation_generation
        active_opener_id = self.wheel.active_robot_wheel_key
        opener_id = (
            active_opener_id
            if active_opener_id is not None
            else self.key_keeps_wheel_opening
        )
        if not self.face_observation_valid:
            self.robot_wheel_observation = (
                generation, False, opener_id, None, None, None
            )
            return
        if opener_id is None:
            self.robot_wheel_observation = (
                generation, True, None, None,
                self.head_angles["pitch"],
                self.head_angles["yaw"],
            )
            return

        opener_state = self.keys_dict.state_dict.get(opener_id)
        if opener_state is None:
            raise RuntimeError(
                f"robot wheel opener {opener_id!r} has no expression state"
            )
        self.robot_wheel_observation = (
            generation,
            True,
            opener_id,
            bool(opener_state["v"]),
            self.head_angles["pitch"],
            self.head_angles["yaw"],
        )


    def set_key_control(self,key_control):
        self.key_control = key_control
        # 如果key_control是False，还需要把self.keys_dict变成None 
        if not key_control:
            self.keys_dict = None

    def decode(self):
        if not self.key_control:
            return
        state_dict = combine_dicts(
            self.keys_dict.state_dict, self.head_dict.state_dict
        )
        if self.action_output == "robot_terminal":
            self._decode_robot_actions(state_dict)
            return
        self._decode_desktop_actions(state_dict)

    def _decode_robot_actions(self, state_dict):
        expressions = self.robot_action_config["expressions"]
        for expression_id, expression_config in expressions.items():
            state = state_dict.get(expression_id)
            if state is None:
                continue
            if state["diff"] is not True or state["cp"] != "FT":
                continue
            if "wheel" in expression_config:
                self.wheel_categories = [
                    resolve_robot_action(
                        self.robot_action_config, action_id, source="wheel"
                    )
                    for action_id in expression_config["wheel"]
                ]
                self.wheel_layout_type = "cardinal"
                self.key_keeps_wheel_opening = expression_id
                continue
            if "action" in expression_config:
                action = resolve_robot_action(
                    self.robot_action_config,
                    expression_config["action"],
                    source="expression",
                )
                self._execute_action(action)

    def _decode_desktop_actions(self, state_dict):
        for k, d in state_dict.items():
            # 如果在configuration里面的那个模式的keys里面才会进这个循环
            keys = self.configuration[self.sys_mode]
            if k not in keys:
                continue
            # 只有在刚转变状态的时候才进入这里
            # 其实这里也不太对，应该设置wheel只有一个的可以连续按
            # 设置0.3s的一个持续按键时间。
            # 一开始这个time是没有被记录的，所以是None，直接就可以跳过所有的了。
            # 如果是连续按压的情况，必须是时间达到，并且按键值是真。防止弄到
            if d['time_True'] is not None:
                time_past_true = time.time() - d['time_True']
                continuous_pressing_condition = (time_past_true > 0.5) and (d['v'])
            else:
                # 这里不能break，因为有些前面的键没有被刷新完状态，就会阻碍后面的键。
                continue
            # if d['v']:
            #     print(f"diff:{d['diff']},continuous_pr但是这个流程里面的触发条件也是不同的essing_condition:{continuous_pressing_condition}")
            if d['diff'] or continuous_pressing_condition:
                # 只要激活了，就应该进入流程里面
                # mouse点击的触发条件是状态改变
                # 锁定眼动控制鼠标这个触发条件只有改变状态为FT。
                # 加入键盘输入队列这个触发条件是改变状态为FT，而且时间条件满足

                # 应当注意按键还需要释放，因为shift和ctrl不释放会有问题。
                # 我觉得用Shift确实是个好事，可以输入大小写和所有的符号，可以设置连续按键时长超过2s就不释放。
                # 这样游戏里面疾跑也不用一直按着了。
                key_config = self.configuration[self.sys_mode][k]
                wheel = key_config['wheel']
                wheel = [str(_) for _ in wheel]
                layout_type = key_config.get('layout_type', 'circle')
                induce = key_config.get('induce', None)
                if induce is not None and d['cp'] == 'FT':
                    lock_mouse_move = induce.get('lock_mouse_move', None)
                    if lock_mouse_move is not None:
                        duration = lock_mouse_move.get('duration', None)
                        self.gaze_mouse_controller.lock_control(duration)
                        # this will be used for lock eye controlled mouse movement util this time
                # 我觉得把要做的action放到队列中，然后有一个函数死循环在执行这些action
                if len(wheel) == 1:
                    # directly control, which can be pressed all the time,
                    # but opening wheel can only press once
                    key_to_press = wheel[0]
                    if key_to_press is not None:
                        # 2024-12-12 16:30:00 改版。
                        # 现在的逻辑变了。
                        # 只要是wheel长度是1，那就用keydown或keyup
                        action = None
                        if d['diff']:
                            # 如果状态改变了，就执行按键
                            # 大部分的按键都是这样的。
                            action = None
                            if d['cp'] == 'FT':
                                action = Action(key_to_press, OpType.KEYDOWN_SAFE)
                            elif d['cp'] == 'TF':
                                action = Action(key_to_press, OpType.KEYUP_SAFE)
                            else:
                                pass
                        else:
                            # 如果状态没有改变，对于按键就什么都不做
                            # 只有鼠标滚轮需要处理
                            if key_to_press.startswith('scroll'):
                                action=Action(
                                    key_to_press, OpType.KEYPRESS
                                )
                        if action is not None:
                            self._execute_action(action)
                else:
                    if d['cp'] == 'FT':
                        # 只有在最初触发的时候会改变这个轮盘
                        self.wheel_categories = wheel
                        self.wheel_layout_type = layout_type
                        self.key_keeps_wheel_opening = k
                        # Wheel callbacks hand selections to action_queue.




from threading import Thread, Lock


class SectorWheel:
    def __init__(self, messagebox, radius=100, subject=None,font_size=14,font="Arial"):
        self.messagebox = messagebox
        self.radius = radius
        self.subject = subject
        self.selected_sector = None
        self.font_size = font_size
        self.font = font

        self.canvas = tk.Canvas(self.messagebox, width=2 * self.radius, height=2 * self.radius, bg='white',
                              highlightthickness=0)
        self.canvas.pack()

        # 初始化位置跟踪
        self.last_op_xy_generation = self.subject.op_xy_generation
        self.canvas.after(10, self.check_op_xy)  # 使用 canvas.after 而不是 self.after
        # print('check_op_xy after')
        # raise Exception('check_op_xy after')
        # exit()
        # 这些属性设置现在可以正常执行了
        self.n_row = 0
        self.n_col = 0
        self.layout_type = 'circle'

    def _screen_to_canvas(self, screen_x: float, screen_y: float) -> tuple[float, float]:
        return (
            screen_x - self.messagebox.winfo_rootx(),
            screen_y - self.messagebox.winfo_rooty(),
        )

    def check_op_xy(self):
        generation = self.subject.published_op_xy_generation
        if generation > self.last_op_xy_generation:
            self.last_op_xy_generation = generation

            class Event:
                pass

            event = Event()
            local_x, local_y = self._screen_to_canvas(*self.subject.op_xy)
            event.x = local_x
            event.y = local_y
            self.on_mouse_move(event)
            # print('check_op_xy on_mouse_moves')
        self.canvas.after(10, self.check_op_xy)  # 使用 canvas.after 而不是 self.after

    def _category_label(self, category: object) -> str:
        if isinstance(category, RobotAction):
            return category.label
        return str(category)

    def update_categories(self, categories, layout_type='circle'):
        if layout_type == 'cardinal' and len(categories) != 4:
            raise ValueError("cardinal layout requires exactly four categories")
        self.last_op_xy_generation = self.subject.op_xy_generation
        self.layout_type = layout_type
        if layout_type == 'square':
            self.n_row = int(len(categories) ** 0.5)
            self.n_col = int(len(categories) ** 0.5) + 1
        self.categories = categories
        self.num_sectors = len(categories)
        if layout_type == 'circle':
            self.draw_sectors()
        elif layout_type == 'square':
            self.draw_square()
        elif layout_type == 'cardinal':
            self.draw_cardinal()
        self.messagebox.deiconify()

    def draw_cardinal(self, highlighted_sector=None):
        self.selected_sector = (
            self.categories[highlighted_sector]
            if highlighted_sector is not None
            else None
        )
        self.canvas.delete("all")
        sectors = (
            (0, 45, self.radius, 0.3 * self.radius),
            (1, 225, self.radius, 1.7 * self.radius),
            (2, 135, 0.3 * self.radius, self.radius),
            (3, 315, 1.7 * self.radius, self.radius),
        )
        for index, start, text_x, text_y in sectors:
            fill_color = (
                "lightgray" if index == highlighted_sector else "white"
            )
            self.canvas.create_arc(
                0, 0, 2 * self.radius, 2 * self.radius,
                start=start, extent=90, fill=fill_color, outline="white",
                width=0, tags=f"sector{index}",
            )
            self.canvas.create_text(
                text_x, text_y,
                text=self._category_label(self.categories[index]),
                font=(self.font, self.font_size * 3, "bold"), fill="red",
            )

    def draw_square(self, highlighted_sector=None):
        self.selected_sector = self.categories[highlighted_sector] if highlighted_sector is not None else None
        self.canvas.delete("all")
        rows, cols = self.n_row, self.n_col
        square_size = 2 * self.radius / max(rows, cols)
        for i in range(rows):
            for j in range(cols):
                idx = i * cols + j
                if idx < self.num_sectors:
                    x1 = j * square_size
                    y1 = i * square_size
                    x2 = x1 + square_size
                    y2 = y1 + square_size
                    fill_color = 'lightgray' if idx == highlighted_sector else 'white'
                    self.canvas.create_rectangle(x1, y1, x2, y2, fill=fill_color, outline='black')
                    self.canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=self._category_label(self.categories[idx]),
                                            font=(self.font, self.font_size, "bold"))

    def draw_sectors(self, highlighted_sector=None):
        self.selected_sector = self.categories[highlighted_sector] if highlighted_sector is not None else None
        self.canvas.delete("all")
        for i in range(self.num_sectors):
            fill_color = 'lightgray' if i == highlighted_sector else 'white'
            outline_color = 'white'
            start_angle = i * (360 / self.num_sectors) + 90
            self.canvas.create_arc(
                0, 0, 2 * self.radius, 2 * self.radius,
                start=start_angle, extent=360 / self.num_sectors,
                fill=fill_color, outline=outline_color, tags=f'sector{i}',
                width=0
            )
            text_angle = math.radians(start_angle + 180 / self.num_sectors)
            text_x = self.radius + 0.7 * self.radius * math.cos(text_angle)
            text_y = self.radius - 0.7 * self.radius * math.sin(text_angle)
            self.canvas.create_text(text_x, text_y, text=self._category_label(self.categories[i]),
                                    font=(self.font, self.font_size*3, "bold"), fill='red')

    def on_mouse_move(self, event):
        if self.layout_type == 'circle':
            angle = self.get_angle_from_mouse_position(event)
            if angle is not None:
                sector = int(angle // (360 / self.num_sectors))
            else:
                sector = None
            self.draw_sectors(highlighted_sector=sector)
        elif self.layout_type == 'square':
            sector = self.get_square_from_mouse_position(event)
            self.draw_square(highlighted_sector=sector)
        elif self.layout_type == 'cardinal':
            sector = self.get_cardinal_from_mouse_position(event)
            self.draw_cardinal(highlighted_sector=sector)

    def get_square_from_mouse_position(self, event):
        rows, cols = self.n_row, self.n_col
        square_size = 2 * self.radius / max(rows, cols)
        col = int(event.x // square_size)
        row = int(event.y // square_size)
        if 0 <= col < cols and 0 <= row < rows:
            idx = row * cols + col
            if idx < self.num_sectors:
                return idx
        return None

    def get_cardinal_from_mouse_position(self, event):
        dx = event.x - self.radius
        dy = event.y - self.radius
        if dx == 0 and dy == 0:
            return None
        if dx * dx + dy * dy > self.radius * self.radius:
            return None
        if abs(dy) >= abs(dx):
            return 0 if dy < 0 else 1
        return 2 if dx < 0 else 3

    def get_angle_from_mouse_position(self, event):
        x = event.x - self.canvas.winfo_width() // 2
        y = self.canvas.winfo_height() // 2 - event.y
        angle = (math.degrees(math.atan2(y, x)) - 90) % 360
        if x ** 2 + y ** 2 > self.radius ** 2:
            return None
        return angle

    def hide(self):
        self.messagebox.withdraw()


class ObserverWithSectorWheel:
    """
    need to start a thread in main call
    get the subject when initializing, subject is the object that this class is listening to
    """

    def __init__(
        self,
        subject: RealAction,
        radius=800,
        layout=None,
        selection=None,
        yaw_threshold_degrees=None,
        pitch_threshold_degrees=None,
        **sector_wheel_config,
    ):
        self.subject = subject
        self.radius = radius
        self.layout = layout
        self.selection = selection
        self.yaw_threshold_degrees = yaw_threshold_degrees
        self.pitch_threshold_degrees = pitch_threshold_degrees
        self.sector_wheel_config = sector_wheel_config
        self.lock = Lock()
        self._thread = None
        self._worker_error = None
        self.root = None
        self.messagebox = None
        self.sector_wheel = None
        self.should_run = False
        self.current_categories = None
        self.selected_sector = None
        self.is_hidden = True
        self.last_robot_observation_generation = None
        self.active_robot_wheel_key = None

    def start(self):
        self.raise_if_failed()
        self.current_categories = None
        self.selected_sector = None
        self.is_hidden = True
        self.last_robot_observation_generation = None
        self.active_robot_wheel_key = None
        if self._thread is not None:
            raise RuntimeError("wheel is already started")
        self.should_run = True
        self._thread = Thread(
            target=self.run_sector_wheel,
            daemon=False,
        )
        try:
            self._thread.start()
        except BaseException:
            self.should_run = False
            self._thread = None
            raise

    def raise_if_failed(self):
        if self._worker_error is None:
            return
        _, error, traceback = self._worker_error
        raise error.with_traceback(traceback)

    def stop(self):
        self.should_run = False
        wheel_thread = self._thread
        if wheel_thread is None:
            self.raise_if_failed()
            return
        if wheel_thread is threading.current_thread():
            raise RuntimeError("wheel thread cannot join itself")
        request_error = None
        root = self.root
        if root is not None:
            try:
                root.after(0, root.destroy)
            except BaseException:
                request_error = sys.exc_info()
        wheel_thread.join()
        self._thread = None
        try:
            self.raise_if_failed()
        except BaseException as error:
            if request_error is not None:
                _, request_exception, _ = request_error
                error.add_note(
                    "wheel root destroy request failed with "
                    f"{type(request_exception).__name__}: {request_exception}"
                )
            raise
        if request_error is not None:
            _, error, traceback = request_error
            raise error.with_traceback(traceback)

    def setup_messagebox(self):
        screen_width = self.messagebox.winfo_screenwidth()
        screen_height = self.messagebox.winfo_screenheight()
        x_cordinate = int((screen_width / 2) - self.radius)
        y_cordinate = int((screen_height / 2) - self.radius)
        self.messagebox.geometry(f"{2 * self.radius}x{2 * self.radius}+{x_cordinate}+{y_cordinate}")

    def run_sector_wheel(self):
        primary_error = None
        try:
            if self.subject.action_output == "robot_terminal":
                if self.layout != "fullscreen_cardinal":
                    raise RuntimeError(
                        "robot terminal requires fullscreen_cardinal wheel"
                    )
                from .cardinal_overlay_x11 import FullscreenCardinalWheel

                if self.selection != "head_pose":
                    raise RuntimeError(
                        "robot terminal requires head_pose wheel selection"
                    )
                self.sector_wheel = FullscreenCardinalWheel(
                    self.subject,
                    yaw_threshold_degrees=self.yaw_threshold_degrees,
                    pitch_threshold_degrees=self.pitch_threshold_degrees,
                )
                self.sector_wheel.start()
                while self.should_run and not self.subject.quit:
                    self.sector_wheel_main_loop(schedule_next=False)
                    time.sleep(0.02)
                return

            self.root = tk.Tk()
            self.root.withdraw()

            self.messagebox = tk.Toplevel(self.root)
            self.messagebox.overrideredirect(True)
            self.messagebox.attributes('-topmost', True)
            self.messagebox.attributes('-alpha', 0.5)
            self.messagebox.withdraw()

            self.sector_wheel = SectorWheel(
                self.messagebox,
                radius=self.radius,
                subject=self.subject,
                **self.sector_wheel_config,
            )
            self.setup_messagebox()
            if self.should_run:
                self.root.after(5000, self.sector_wheel_main_loop)
            else:
                self.root.after(0, self.root.destroy)
            self.root.mainloop()
        except BaseException:
            primary_error = sys.exc_info()
            self.should_run = False
        finally:
            if primary_error is None and self._worker_error is not None:
                primary_error = self._worker_error
            if (
                self.subject.action_output == "robot_terminal"
                and self.sector_wheel is not None
            ):
                try:
                    self.sector_wheel.stop()
                except BaseException as cleanup_error:
                    if primary_error is None:
                        primary_error = sys.exc_info()
                    else:
                        primary_error[1].add_note(
                            "robot action overlay cleanup failed with "
                            f"{type(cleanup_error).__name__}: {cleanup_error}"
                        )
            if primary_error is not None:
                self._worker_error = primary_error
            self.should_run = False
            self.root = None
            self.messagebox = None
            self.sector_wheel = None

    def sector_wheel_main_loop(self, schedule_next=True):
        try:
            if not self.should_run or self.subject.quit:
                if self.root is not None:
                    self.root.destroy()
                return
            if self.subject.keys_dict is not None:
                with self.lock:
                    categories = self.subject.wheel_categories
                    key = self.subject.key_keeps_wheel_opening
                    if categories is not None and key is not None:
                        new_categories = self.subject.wheel_categories
                        key_is_active = (
                            self.subject.keys_dict.state_dict[key]["v"]
                        )
                        if self.subject.action_output == "robot_terminal":
                            if self.is_hidden and key_is_active:
                                self.sector_wheel.update_categories(
                                    new_categories,
                                    layout_type=self.subject.wheel_layout_type,
                                )
                                self.last_robot_observation_generation = None
                                self.active_robot_wheel_key = key
                                self.is_hidden = False
                            elif not self.is_hidden:
                                observation = (
                                    self.subject.robot_wheel_observation
                                )
                                if (
                                    observation is not None
                                    and observation[0]
                                    != self.last_robot_observation_generation
                                ):
                                    (
                                        generation,
                                        face_detected,
                                        opener_id,
                                        opener_active,
                                        pitch,
                                        yaw,
                                    ) = observation
                                    self.last_robot_observation_generation = (
                                        generation
                                    )
                                    if (
                                        opener_id
                                        != self.active_robot_wheel_key
                                    ):
                                        decision = None
                                    else:
                                        decision = (
                                            self.sector_wheel.observe_control_frame(
                                                face_detected=face_detected,
                                                opener_active=opener_active,
                                                pitch=pitch,
                                                yaw=yaw,
                                            )
                                        )
                                    if decision in ("submit", "cancel"):
                                        self.sector_wheel.hide()
                                        selected = (
                                            self.sector_wheel.selected_sector
                                            if decision == "submit"
                                            else None
                                        )
                                        action = (
                                            self.subject.make_wheel_action(
                                                selected
                                            )
                                        )
                                        if action is not None:
                                            self.subject.action_queue.put(
                                                action
                                            )
                                        self.is_hidden = True
                                        self.active_robot_wheel_key = None
                                        self.subject.key_keeps_wheel_opening = None
                        elif key_is_active:
                            if self.is_hidden:
                                desktop.move_pointer(
                                    *self.subject.mid_point, relative=False
                                )
                                self.sector_wheel.update_categories(
                                    new_categories,
                                    layout_type=self.subject.wheel_layout_type,
                                )
                                self.is_hidden = False
                        elif not self.is_hidden:
                            self.sector_wheel.hide()
                            selected = self.sector_wheel.selected_sector
                            action = self.subject.make_wheel_action(selected)
                            if action is not None:
                                self.subject.action_queue.put(action)
                            self.is_hidden = True
            if (
                schedule_next
                and self.should_run
                and not self.subject.quit
            ):
                self.root.after(20, self.sector_wheel_main_loop)
        except BaseException:
            self._worker_error = sys.exc_info()
            self.should_run = False
            if self.root is not None:
                self.root.destroy()
