"""
Kalman-style motion model with variable delta time.
"""
import numpy as np

class KalmanFilter2D:
    def __init__(self, q_vel: float = 10.0, r_pos: float = 1.0):
        # State [x, y, vx, vy]
        self.x = np.zeros((4,1))
        self.P = np.eye(4) * 100.0
        self.q_vel = q_vel
        self.r_pos = r_pos
        self.initialized = False

    def init(self, x: float, y: float, vx: float = 0, vy: float = 0):
        self.x = np.array([[x],[y],[vx],[vy]], dtype=float)
        self.P = np.eye(4) * 10.0
        self.initialized = True

    def predict(self, dt: float):
        if not self.initialized:
            return
        if dt <= 0:
            dt = 1/30.0
        F = np.array([
            [1,0,dt,0],
            [0,1,0,dt],
            [0,0,1,0],
            [0,0,0,1]
        ], dtype=float)
        # Process noise: scales with dt
        q = self.q_vel
        Q = np.array([
            [0,0,0,0],
            [0,0,0,0],
            [0,0,q*dt,0],
            [0,0,0,q*dt]
        ], dtype=float)
        # Add small pos noise
        Q[0,0] = 0.1 * dt
        Q[1,1] = 0.1 * dt

        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q

    def update(self, z_x: float, z_y: float, r_scale: float = 1.0):
        if not self.initialized:
            self.init(z_x, z_y)
            return
        H = np.array([
            [1,0,0,0],
            [0,1,0,0]
        ], dtype=float)
        z = np.array([[z_x],[z_y]], dtype=float)
        R = np.eye(2) * (self.r_pos * r_scale)
        y = z - H @ self.x
        S = H @ self.P @ H.T + R
        try:
            K = self.P @ H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            return
        self.x = self.x + K @ y
        I = np.eye(4)
        self.P = (I - K @ H) @ self.P

    def get_pos(self):
        return float(self.x[0,0]), float(self.x[1,0])

    def get_velocity(self):
        return float(self.x[2,0]), float(self.x[3,0])

    def get_covariance(self):
        return self.P

    def gating_distance(self, z_x: float, z_y: float) -> float:
        """Mahalanobis distance."""
        if not self.initialized:
            return 0
        H = np.array([[1,0,0,0],[0,1,0,0]], dtype=float)
        z = np.array([[z_x],[z_y]], dtype=float)
        y = z - H @ self.x
        S = H @ self.P @ H.T + np.eye(2)*self.r_pos
        try:
            invS = np.linalg.inv(S)
            dist = float(y.T @ invS @ y)
            return dist
        except:
            return float('inf')

    def inflate_covariance(self, factor: float = 1.5):
        self.P *= factor
