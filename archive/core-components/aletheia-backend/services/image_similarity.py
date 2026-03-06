"""
图片相似度检测服务 - 使用感知哈希和OpenCV
"""

import os
import hashlib
from typing import Optional, List, Tuple
import asyncio
from io import BytesIO
from datetime import datetime

from utils.logging import logger
from utils.stability import retry_async, CircuitBreaker


class ImageSimilarityService:
    """图片相似度检测服务"""

    def __init__(self):
        """初始化服务"""
        self.circuit_breaker = CircuitBreaker(
            "image_similarity",
            failure_threshold=3,
            recovery_timeout=60,
        )
        self._init_libraries()

    def _init_libraries(self):
        """初始化依赖库"""
        try:
            import cv2
            import numpy as np
            from PIL import Image

            self.cv2 = cv2
            self.np = np
            self.Image = Image
            logger.info("✅ Image similarity service initialized")
        except ImportError as e:
            logger.warning(
                f"⚠️ Image similarity dependencies not installed: {e}\n"
                "Install with: pip install opencv-python pillow numpy"
            )
            self.cv2 = None
            self.np = None
            self.Image = None

    async def download_image(self, url: str) -> Optional[bytes]:
        """
        下载图片

        Args:
            url: 图片URL

        Returns:
            图片字节数据
        """
        if not url:
            return None

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        return await response.read()
                    else:
                        logger.warning(
                            f"⚠️ Failed to download image: {url} (status: {response.status})"
                        )
                        return None
        except Exception as e:
            logger.error(f"❌ Error downloading image {url}: {e}")
            return None

    def calculate_phash(self, image_bytes: bytes, hash_size: int = 8) -> Optional[str]:
        """
        计算感知哈希（pHash）

        Args:
            image_bytes: 图片字节数据
            hash_size: 哈希大小（默认8x8=64位）

        Returns:
            感知哈希值（十六进制字符串）
        """
        if not self.Image or not self.np:
            logger.warning("⚠️ PIL or numpy not available")
            return None

        try:
            # 打开图片
            img = self.Image.open(BytesIO(image_bytes))

            # 转换为灰度图
            img = img.convert("L")

            # 调整大小
            img = img.resize((hash_size, hash_size), self.Image.Resampling.LANCZOS)

            # 转换为numpy数组
            pixels = self.np.asarray(img)

            # 计算DCT（离散余弦变换）
            dct = self._calculate_dct(pixels)

            # 取左上角hash_size x hash_size区域
            dct_low_freq = dct[:hash_size, :hash_size]

            # 计算平均值
            avg = dct_low_freq.mean()

            # 生成哈希
            diff = dct_low_freq > avg

            # 转换为十六进制字符串
            hash_value = 0
            for i, row in enumerate(diff):
                for j, val in enumerate(row):
                    if val:
                        hash_value |= 1 << (i * hash_size + j)

            return hex(hash_value)[2:].zfill(16)

        except Exception as e:
            logger.error(f"❌ Error calculating phash: {e}")
            return None

    def _calculate_dct(self, image: "np.ndarray") -> "np.ndarray":
        """
        计算离散余弦变换（DCT）

        Args:
            image: 图片数组

        Returns:
            DCT结果
        """
        if not self.cv2:
            # 简化版DCT（使用numpy）
            return self._simple_dct(image)

        # 使用OpenCV的DCT
        dct = self.cv2.dct(self.np.float32(image))
        return dct

    def _simple_dct(self, image: "np.ndarray") -> "np.ndarray":
        """简化版DCT（不依赖OpenCV）"""
        # 这里使用简化的DCT实现
        # 实际上应该使用scipy.fftpack.dct，但为了减少依赖，使用简化版本
        size = image.shape[0]
        dct = self.np.zeros_like(image, dtype=float)

        for u in range(size):
            for v in range(size):
                sum_val = 0.0
                for x in range(size):
                    for y in range(size):
                        sum_val += (
                            image[x, y]
                            * self.np.cos(self.np.pi * (2 * x + 1) * u / (2.0 * size))
                            * self.np.cos(self.np.pi * (2 * y + 1) * v / (2.0 * size))
                        )

                alpha_u = 1 / self.np.sqrt(size) if u == 0 else self.np.sqrt(2.0 / size)
                alpha_v = 1 / self.np.sqrt(size) if v == 0 else self.np.sqrt(2.0 / size)
                dct[u, v] = alpha_u * alpha_v * sum_val

        return dct

    def hamming_distance(self, hash1: str, hash2: str) -> int:
        """
        计算汉明距离

        Args:
            hash1: 哈希值1
            hash2: 哈希值2

        Returns:
            汉明距离（不同位的数量）
        """
        if not hash1 or not hash2:
            return 64  # 最大距离

        try:
            # 转换为整数
            int1 = int(hash1, 16)
            int2 = int(hash2, 16)

            # 计算XOR
            xor = int1 ^ int2

            # 计算1的个数（汉明距离）
            distance = bin(xor).count("1")
            return distance

        except Exception as e:
            logger.error(f"❌ Error calculating hamming distance: {e}")
            return 64

    def calculate_similarity(self, hash1: str, hash2: str) -> float:
        """
        计算相似度（0.0-1.0）

        Args:
            hash1: 哈希值1
            hash2: 哈希值2

        Returns:
            相似度分数（0.0=完全不同，1.0=完全相同）
        """
        distance = self.hamming_distance(hash1, hash2)
        # 64位哈希，最大距离64
        similarity = 1.0 - (distance / 64.0)
        return similarity

    async def compare_images(self, url1: str, url2: str) -> Optional[dict]:
        """
        比较两张图片的相似度

        Args:
            url1: 图片1的URL
            url2: 图片2的URL

        Returns:
            比较结果
        """
        try:
            # 下载图片
            img1_bytes, img2_bytes = await asyncio.gather(
                self.download_image(url1),
                self.download_image(url2),
            )

            if not img1_bytes or not img2_bytes:
                logger.warning("⚠️ Failed to download one or both images")
                return None

            # 计算哈希
            hash1 = self.calculate_phash(img1_bytes)
            hash2 = self.calculate_phash(img2_bytes)

            if not hash1 or not hash2:
                logger.warning("⚠️ Failed to calculate hash for one or both images")
                return None

            # 计算相似度
            similarity = self.calculate_similarity(hash1, hash2)
            distance = self.hamming_distance(hash1, hash2)

            result = {
                "url1": url1,
                "url2": url2,
                "hash1": hash1,
                "hash2": hash2,
                "similarity": similarity,
                "hamming_distance": distance,
                "is_similar": similarity > 0.9,  # 90%以上认为相似
                "is_identical": similarity > 0.95,  # 95%以上认为identical
                "timestamp": datetime.utcnow().isoformat(),
            }

            logger.info(
                f"✅ Image comparison: similarity={similarity:.2%}, distance={distance}"
            )
            return result

        except Exception as e:
            logger.error(f"❌ Error comparing images: {e}")
            return None

    async def find_duplicates(
        self, image_urls: List[str], similarity_threshold: float = 0.9
    ) -> List[Tuple[str, str, float]]:
        """
        在图片列表中查找重复/相似的图片

        Args:
            image_urls: 图片URL列表
            similarity_threshold: 相似度阈值

        Returns:
            重复图片对列表 [(url1, url2, similarity), ...]
        """
        if len(image_urls) < 2:
            return []

        logger.info(f"🔍 Finding duplicates in {len(image_urls)} images...")

        # 下载所有图片并计算哈希
        tasks = [self.download_image(url) for url in image_urls]
        image_bytes_list = await asyncio.gather(*tasks, return_exceptions=True)

        # 计算所有哈希值
        hashes = []
        valid_urls = []
        for i, (url, img_bytes) in enumerate(zip(image_urls, image_bytes_list)):
            if isinstance(img_bytes, Exception) or not img_bytes:
                continue

            hash_val = self.calculate_phash(img_bytes)
            if hash_val:
                hashes.append(hash_val)
                valid_urls.append(url)

        if len(hashes) < 2:
            logger.warning("⚠️ Not enough valid images to compare")
            return []

        # 比较所有图片对
        duplicates = []
        for i in range(len(hashes)):
            for j in range(i + 1, len(hashes)):
                similarity = self.calculate_similarity(hashes[i], hashes[j])

                if similarity >= similarity_threshold:
                    duplicates.append((valid_urls[i], valid_urls[j], similarity))

        logger.info(f"✅ Found {len(duplicates)} duplicate/similar image pairs")
        return duplicates

    async def detect_manipulated_image(
        self, image_url: str, reference_urls: List[str]
    ) -> dict:
        """
        检测图片是否被篡改（PS、裁剪等）

        Args:
            image_url: 待检测图片URL
            reference_urls: 参考图片URL列表（原始图片）

        Returns:
            检测结果
        """
        logger.info(f"🔍 Detecting image manipulation for: {image_url}")

        # 下载待检测图片
        target_bytes = await self.download_image(image_url)
        if not target_bytes:
            return {"error": "Failed to download target image"}

        target_hash = self.calculate_phash(target_bytes)
        if not target_hash:
            return {"error": "Failed to calculate target hash"}

        # 与所有参考图片比较
        comparisons = []
        for ref_url in reference_urls:
            result = await self.compare_images(image_url, ref_url)
            if result:
                comparisons.append(result)

        if not comparisons:
            return {
                "is_manipulated": False,
                "confidence": 0.0,
                "message": "No reference images available for comparison",
            }

        # 找到最相似的参考图片
        best_match = max(comparisons, key=lambda x: x["similarity"])

        # 判断是否被篡改
        is_manipulated = 0.7 < best_match["similarity"] < 0.95

        result = {
            "target_url": image_url,
            "is_manipulated": is_manipulated,
            "confidence": best_match["similarity"],
            "best_match_url": best_match["url2"],
            "hamming_distance": best_match["hamming_distance"],
            "analysis": self._analyze_manipulation(best_match["similarity"]),
            "all_comparisons": comparisons,
            "timestamp": datetime.utcnow().isoformat(),
        }

        logger.info(
            f"✅ Manipulation detection: is_manipulated={is_manipulated}, "
            f"confidence={best_match['similarity']:.2%}"
        )
        return result

    def _analyze_manipulation(self, similarity: float) -> str:
        """分析篡改类型"""
        if similarity > 0.95:
            return "IDENTICAL - Likely the same image"
        elif similarity > 0.9:
            return "MINOR_CHANGES - Possibly compressed or resized"
        elif similarity > 0.8:
            return "MODERATE_CHANGES - Likely cropped or color-adjusted"
        elif similarity > 0.7:
            return "SIGNIFICANT_CHANGES - Heavily edited or partially manipulated"
        else:
            return "DIFFERENT - Not the same image"


# 全局单例
_image_similarity_service: Optional[ImageSimilarityService] = None


def get_image_similarity_service() -> ImageSimilarityService:
    """获取图片相似度服务单例"""
    global _image_similarity_service

    if _image_similarity_service is None:
        _image_similarity_service = ImageSimilarityService()

    return _image_similarity_service
