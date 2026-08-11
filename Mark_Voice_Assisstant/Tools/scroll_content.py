import asyncio
import pyautogui
from typing import Optional, Literal
from functools import wraps
import logging
from dataclasses import dataclass
from enum import Enum
from livekit.agents import function_tool  # ✅ Correct import

class ScrollDirection(Enum):
    UP = "up"
    DOWN = "down"

@dataclass
class ScreenDimensions:
    width: int
    height: int

class ScrollControllerError(Exception):
    """Custom exception for scroll operations"""
    pass

class ScrollController:
    """
    Advanced Scroll Controller with optimized scrolling operations
    """
    
    def __init__(self):
        self.logger = self._setup_logger()
        self.scroll_speed_factor = 0.5
        self.animation_duration = 0.1
        
    def _setup_logger(self) -> logging.Logger:
        """Setup advanced logging"""
        logger = logging.getLogger('ScrollController')
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    async def _get_screen_dimensions(self) -> ScreenDimensions:
        """Get screen dimensions asynchronously"""
        try:
            width, height = await asyncio.to_thread(pyautogui.size)
            return ScreenDimensions(width=width, height=height)
        except Exception as e:
            raise ScrollControllerError(f"Failed to get screen dimensions: {str(e)}")

    async def _move_to_center(self, screen: ScreenDimensions):
        """Move mouse to screen center for optimal scrolling"""
        try:
            await asyncio.to_thread(
                pyautogui.moveTo, 
                screen.width // 2, 
                screen.height // 2, 
                duration=self.animation_duration
            )
            self.logger.debug("Mouse moved to screen center")
        except Exception as e:
            raise ScrollControllerError(f"Failed to move mouse to center: {str(e)}")

    async def _calculate_scroll_amount(
        self, 
        direction: Literal["up", "down"], 
        amount: int
    ) -> int:
        """Calculate final scroll amount with direction"""
        base_amount = amount * self.scroll_speed_factor
        
        if direction == ScrollDirection.UP.value:
            return int(base_amount)
        elif direction == ScrollDirection.DOWN.value:
            return int(-base_amount)
        else:
            raise ScrollControllerError(f"Invalid scroll direction: {direction}")

    async def _perform_scroll(self, scroll_amount: int):
        """Perform the actual scroll operation"""
        try:
            await asyncio.to_thread(pyautogui.scroll, scroll_amount)
            self.logger.debug(f"Scrolled by {scroll_amount} units")
        except Exception as e:
            raise ScrollControllerError(f"Scroll execution failed: {str(e)}")

    @function_tool()  # ✅ Now using the correct LiveKit function_tool
    async def scroll_content(
        self, 
        direction: Optional[Literal["up", "down"]] = None,
        amount: Optional[int] = 3
    ) -> str:
        """
        Advanced scrolling functionality with optimized performance
        
        Args:
            direction: Scroll direction ("up" or "down")
            amount: Number of scroll units (default: 3)
            
        Returns:
            str: Scroll confirmation in Hindi
        """
        # Set defaults
        direction = direction or ScrollDirection.UP.value
        amount = amount or 3
        
        self.logger.info(f"Scroll requested: direction={direction}, amount={amount}")
        
        # Validate inputs
        if direction not in [ScrollDirection.UP.value, ScrollDirection.DOWN.value]:
            raise ScrollControllerError(f"Invalid scroll direction: {direction}")
        
        if amount <= 0:
            raise ScrollControllerError("Scroll amount must be positive")
        
        try:
            # Get screen dimensions and move to center
            screen = await self._get_screen_dimensions()
            await self._move_to_center(screen)
            
            # Calculate and perform scroll
            scroll_amount = await self._calculate_scroll_amount(direction, amount)
            await self._perform_scroll(scroll_amount)
            
            return f"✅ सफलतापूर्वक {direction} की ओर {amount} यूनिट स्क्रॉल किया।"
            
        except Exception as e:
            self.logger.error(f"Scroll operation failed: {str(e)}")
            return f"❌ स्क्रॉल करने में विफल: {str(e)}"

    async def scroll_up(self, amount: int = 3) -> str:
        """Convenience method for scrolling up"""
        return await self.scroll_content("up", amount)

    async def scroll_down(self, amount: int = 3) -> str:
        """Convenience method for scrolling down"""
        return await self.scroll_content("down", amount)

# Global instance for easy access
scroll_controller = ScrollController()

# Direct function access with LiveKit function_tool decorator
@function_tool()
async def scroll_content(
    direction: Optional[Literal["up", "down"]] = None,
    amount: Optional[int] = 3
) -> str:
    """Main scroll function with LiveKit function_tool decorator"""
    return await scroll_controller.scroll_content(direction, amount)