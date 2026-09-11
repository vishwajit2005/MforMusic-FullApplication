package com.mformusic.frontend.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

private fun musicText(size: Int, height: Int, weight: FontWeight = FontWeight.Normal) = TextStyle(
    fontFamily = FontFamily.SansSerif, fontWeight = weight,
    fontSize = size.sp, lineHeight = height.sp, letterSpacing = 0.sp
)
val Typography = Typography(
    displaySmall = musicText(36, 42, FontWeight.ExtraBold),
    headlineLarge = musicText(32, 38, FontWeight.ExtraBold),
    headlineMedium = musicText(28, 34, FontWeight.Bold),
    headlineSmall = musicText(24, 30, FontWeight.Bold),
    titleLarge = musicText(22, 28, FontWeight.Bold),
    titleMedium = musicText(16, 22, FontWeight.SemiBold),
    titleSmall = musicText(14, 20, FontWeight.SemiBold),
    bodyLarge = musicText(16, 24), bodyMedium = musicText(14, 20),
    bodySmall = musicText(12, 18), labelLarge = musicText(14, 20, FontWeight.Bold),
    labelMedium = musicText(12, 16, FontWeight.SemiBold),
    labelSmall = musicText(11, 16, FontWeight.Medium)
)
