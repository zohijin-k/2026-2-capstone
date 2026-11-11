"""Experimental, opt-in exterior document quadrilateral rectification.

This module is deliberately not called by engine preprocessing. It uses pixels
only, never synthetic geometry, OCR text, ground truth or document templates.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image


@dataclass
class Rectification:
    image: Image.Image
    applied: bool
    matrix: np.ndarray  # input pixel -> output pixel homogeneous transform
    corners: list[list[float]] | None = None


def _order_corners(points):
    points = np.asarray(points, dtype=np.float32).reshape(4, 2)
    # Convex contour vertices are cyclic; start at top-left, clockwise.
    center = points.mean(axis=0)
    angles = np.arctan2(points[:,1]-center[1], points[:,0]-center[0])
    points = points[np.argsort(angles)]
    points = np.roll(points, -np.argmin(points.sum(axis=1)), axis=0)
    return points


def rectify_document(image: Image.Image) -> Rectification:
    """Find a large convex 4-corner boundary, flatten it, or return unchanged.

    Boundaries touching the frame and tiny interior text/table rectangles are
    rejected. Failure is explicit; the original image is retained on failure.
    No image enhancement or interpolation is done unless a boundary is found.
    """
    rgb = np.asarray(image.convert('RGB'))
    height, width = rgb.shape[:2]
    scale = min(1.0, 1200 / max(width, height))
    small = cv2.resize(rgb, (round(width*scale), round(height*scale)))
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY), (5,5), 0)
    masks = [cv2.Canny(gray, 25, 75)]
    # Different exposures/shadows can split an Otsu mask; fixed alternatives
    # permit the continuous exterior boundary to survive without known corners.
    masks += [cv2.threshold(gray, level, 255, cv2.THRESH_BINARY)[1]
              for level in (105, 125, 155, 185)]
    best = None
    best_area = 0
    total_area = gray.shape[0] * gray.shape[1]
    for mask in masks:
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5,5),np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            perimeter = cv2.arcLength(contour, True)
            quad = cv2.approxPolyDP(contour, .02*perimeter, True)
            if len(quad) != 4 or not cv2.isContourConvex(quad):
                continue
            area = cv2.contourArea(quad)
            points = quad.reshape(4,2)
            if not .35*total_area < area < .97*total_area:
                continue
            if np.any(points < 2) or np.any(points[:,0] >= gray.shape[1]-2) or np.any(points[:,1] >= gray.shape[0]-2):
                continue
            if area > best_area:
                best, best_area = points, area
    if best is None:
        return Rectification(image.copy(), False, np.eye(3))
    corners = _order_corners(best/scale)
    tl, tr, br, bl = corners
    out_w = round(max(np.linalg.norm(tr-tl), np.linalg.norm(br-bl)))
    out_h = round(max(np.linalg.norm(bl-tl), np.linalg.norm(br-tr)))
    if min(out_w, out_h) < 32:
        return Rectification(image.copy(), False, np.eye(3))
    destination = np.float32([[0,0],[out_w-1,0],[out_w-1,out_h-1],[0,out_h-1]])
    matrix = cv2.getPerspectiveTransform(corners, destination)
    warped = cv2.warpPerspective(rgb, matrix, (out_w,out_h), flags=cv2.INTER_CUBIC)
    return Rectification(Image.fromarray(warped), True, matrix, corners.tolist())
