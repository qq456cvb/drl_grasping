from drl_grasping.control import MoveIt2
from drl_grasping.utils.math import quat_mul
from drl_grasping.utils.conversions import orientation_6d_to_quat
from gym_ignition.base import task
from gym_ignition.rbd import conversions
from gym_ignition.utils.typing import Action, Reward, Observation
from gym_ignition.utils.typing import ActionSpace, ObservationSpace
from itertools import count
from scipy.spatial.transform import Rotation
from typing import Tuple, Union
import abc
import gym
import numpy as np


class Manipulation(task.Task, abc.ABC):
    _ids = count(0)

    # Parameters for ManipulationGazeboEnvRandomizer
    _robot_model: str = 'panda'
    _robot_position: Tuple[float, float, float] = (0, 0, 0)
    _robot_quat_xyzw: Tuple[float, float, float, float] = (0, 0, 0, 1)
    _robot_arm_collision: bool = True
    _robot_hand_collision: bool = True
    _robot_initial_joint_positions: Tuple[float, ...] = (0.0,
                                                         0.0,
                                                         0.0,
                                                         -1.57,
                                                         0.0,
                                                         1.57,
                                                         0.79,
                                                         0.04,
                                                         0.04)

    _camera_enable: bool = False
    _camera_type: str = 'rgbd_camera'
    _camera_render_engine: str = 'ogre2'
    _camera_position: Tuple[float, float, float] = (0.5, 0, 1)
    _camera_quat_xyzw: Tuple[float, float,
                             float, float] = (-0.707, 0, 0.707, 0)
    _camera_width: int = 128
    _camera_height: int = 128
    _camera_update_rate: int = 10
    _camera_horizontal_fov: float = 1.0
    _camera_vertical_fov: float = 1.0
    _camera_clip_color: Tuple[float, float] = (0.01, 1000.0)
    _camera_clip_depth: Tuple[float, float] = (0.01, 10.0)
    _camera_ros2_bridge_color: bool = False
    _camera_ros2_bridge_depth: bool = False
    _camera_ros2_bridge_points: bool = False

    _ground_enable: bool = False
    _ground_position: Tuple[float, float, float] = (0.5, 0, 0)
    _ground_quat_xyzw: Tuple[float, float, float, float] = (0, 0, 0, 1)
    _ground_size: Tuple[float, float] = (0.5, 0.5)

    _object_enable: bool = False
    _object_type: str = 'box'
    _workspace_centre: Tuple[float, float, float] = (0.5, 0, 0)
    _workspace_volume: Tuple[float, float, float] = (0.75, 0.75, 0.75)
    _object_spawn_volume: Tuple[float, float, float] = (0.5, 0.5, 0.05)
    _object_spawn_height: float = 0.025
    _object_quat_xyzw: Tuple[float, float, float, float] = (0, 0, 0, 1)
    _object_size: Tuple[float, float, float] = (0.05, 0.05, 0.05)
    _object_mass: float = 0.1
    _object_collision: bool = True
    _object_visual: bool = True
    _object_static: bool = False
    _object_color: Tuple[float, float, float, float] = (0.8, 0.8, 0.8, 1.0)

    _insert_scene_broadcaster_plugin: bool = True
    _insert_user_commands_plugin: bool = False

    def __init__(self,
                 agent_rate: float,
                 restrict_position_goal_to_workspace: bool,
                 verbose: bool,
                 **kwargs):
        # Add to ids
        self.id = next(self._ids)

        # Initialize the Task base class
        task.Task.__init__(self, agent_rate=agent_rate)

        # Control (MoveIt2)
        self.moveit2 = MoveIt2(node_name=f'ign_moveit2_py_{self.id}')

        # Names of important models
        self.robot_name = None
        self.robot_base_link_name = None
        self.robot_ee_link_name = None
        self.robot_gripper_link_names = []
        self.camera_name = None
        self.ground_name = None
        self.object_names = []

        # Additional parameters
        self._restrict_position_goal_to_workspace = restrict_position_goal_to_workspace
        self._verbose = verbose

    def create_spaces(self) -> Tuple[ActionSpace, ObservationSpace]:

        # Action space
        action_space = self.create_action_space()
        # Observation space
        observation_space = self.create_observation_space()

        return action_space, observation_space

    def create_action_space(self) -> ActionSpace:

        pass

    def create_observation_space(self) -> ObservationSpace:

        pass

    def set_action(self, action: Action) -> None:

        pass

    def get_observation(self) -> Observation:

        pass

    def get_reward(self) -> Reward:

        pass

    def is_done(self) -> bool:

        pass

    def reset_task(self) -> None:

        pass

    def set_position_goal(self,
                          absolute: Union[Tuple[float, float, float],
                                          None] = None,
                          relative: Union[Tuple[float, float, float],
                                          None] = None,
                          relative_position_scaling_factor: float = 0.1):

        target_pos = None

        if absolute is not None:
            # If absolute position is selected, simple use the action as the target
            target_pos = absolute
        elif relative is not None:
            # Scale relative action to metric units
            relative_pos = relative_position_scaling_factor * relative
            # Get current position
            current_pos = self.get_ee_position()

            # Compute target position
            target_pos = [current_pos[0] + relative_pos[0],
                          current_pos[1] + relative_pos[1],
                          current_pos[2] + relative_pos[2]]

        if target_pos is not None:
            # Restrict target position to a limited workspace
            if self._restrict_position_goal_to_workspace:
                centre = self._workspace_centre
                volume = self._workspace_volume
                for i in range(3):
                    target_pos[i] = min(centre[i] + volume[i]/2,
                                        max(centre[i] - volume[i]/2,
                                            target_pos[i]))
            # Set position goal
            self.moveit2.set_position_goal(target_pos)
        else:
            print('error: Neither absolute or relative position is set')

    def set_orientation_goal(self,
                             absolute: Union[Tuple[float, ...], None] = None,
                             relative: Union[Tuple[float, ...], None] = None,
                             representation: str = 'quat',
                             xyzw: bool = True,
                             z_relative_orientation_scaling_factor: float = np.pi/4.0):

        target_quat_xyzw = None

        if absolute is not None:
            # Convert absolute orientation representation to quaternion
            if 'quat' == representation:
                if xyzw:
                    target_quat_xyzw = absolute
                else:
                    target_quat_xyzw = conversions.Quaternion.to_xyzw(absolute)
            elif '6d' == representation:
                vectors = tuple(absolute[x:x + 3] for x, _ in enumerate(absolute) if x % 3 == 0) 
                target_quat_xyzw = orientation_6d_to_quat(vectors[0], vectors[1])
            elif 'z' == representation:
                target_quat_xyzw = Rotation.from_euler('xyz', [np.pi, 0, absolute]).as_quat()

        elif relative is not None:
            # Get current orientation
            current_quat_xyzw = conversions.Quaternion.to_xyzw(
                self.get_ee_orientation())

            # For 'z' representation, result should always point down
            # Therefore, create a new quatertnion that contains only yaw component
            if 'z' == representation:
                current_yaw = Rotation.from_quat(current_quat_xyzw).as_euler('xyz')[2]
                current_quat_xyzw = Rotation.from_euler('xyz', [np.pi, 0, current_yaw]).as_quat()

            # Convert relative orientation representation to quaternion
            relative_quat_xyzw = None
            if 'quat' == representation:
                if xyzw:
                    relative_quat_xyzw = relative
                else:
                    relative_quat_xyzw = \
                        conversions.Quaternion.to_xyzw(relative)
            elif '6d' == representation:
                vectors = tuple(relative[x:x + 3] for x, _ in enumerate(relative) if x % 3 == 0) 
                relative_quat_xyzw = orientation_6d_to_quat(vectors[0], vectors[1])
            elif 'z' == representation:
                relative *= z_relative_orientation_scaling_factor
                relative_quat_xyzw = Rotation.from_euler('xyz', [0, 0, relative]).as_quat()

            # Compute target position (combine quaternions)
            target_quat_xyzw = quat_mul(current_quat_xyzw, relative_quat_xyzw)

        if target_quat_xyzw is not None:
            # Normalise quaternion (should not be needed, but just to be safe)
            target_quat_xyzw /= np.linalg.norm(target_quat_xyzw)
            # Set orientation goal
            self.moveit2.set_orientation_goal(target_quat_xyzw)
        else:
            print('error: Neither absolute or relative orientation is set')

    def get_ee_position(self) -> Tuple[float, float, float]:

        robot = self.world.get_model(self.robot_name).to_gazebo()
        return robot.get_link(self.robot_ee_link_name).position()

    def get_ee_orientation(self) -> Tuple[float, float, float, float]:
        """
        Return the current wxyz quaternion of the end effector
        """

        robot = self.world.get_model(self.robot_name).to_gazebo()
        return robot.get_link(self.robot_ee_link_name).orientation()
