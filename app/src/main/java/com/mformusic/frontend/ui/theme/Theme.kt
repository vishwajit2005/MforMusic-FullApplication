package com.mformusic.frontend.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val MforMusicDarkColorScheme = darkColorScheme(
    primary = SpotifyGreen,
    onPrimary = TextPrimary,
    primaryContainer = DarkCard,
    secondary = SpotifyGreenLight,
    background = DarkBackground,
    surface = DarkSurface,
    surfaceVariant = DarkCard,
    onBackground = TextPrimary,
    onSurface = TextPrimary,
    onSurfaceVariant = TextSecondary,
    error = ErrorRed
)

@Composable
fun MforMusicTheme(content: @Composable () -> Unit) {
    // Always dark — music apps should never switch to light mode
    MaterialTheme(
        colorScheme = MforMusicDarkColorScheme,
        typography = Typography,
        content = content
    )
}