package com.mformusic.frontend.ui.components

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import coil.request.ImageRequest
import com.mformusic.frontend.ui.theme.*

@Composable
fun AlbumArtwork(url: String?, modifier: Modifier = Modifier) {
    Box(modifier.clip(RoundedCornerShape(16.dp)).background(
        Brush.linearGradient(listOf(GradientTop, DarkCardElevated))), contentAlignment = Alignment.Center) {
        Icon(Icons.Default.MusicNote, null, tint = Accent, modifier = Modifier.size(32.dp))
        AsyncImage(model = ImageRequest.Builder(LocalContext.current).data(url).crossfade(250).build(),
            contentDescription = null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
    }
}

@Composable
fun PlaybackButton(icon: ImageVector, label: String, onClick: () -> Unit,
                   prominent: Boolean = false, size: Dp = 48.dp, enabled: Boolean = true) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val scale by animateFloatAsState(if (pressed) 0.90f else 1f, label = "playback_press")
    IconButton(onClick = onClick, enabled = enabled, interactionSource = interaction,
        modifier = Modifier.size(size).scale(scale).clip(CircleShape)
            .background(if (prominent) Accent else DarkCard.copy(alpha = 0.3f))) {
        Icon(icon, label, tint = if (!enabled) TextMuted else if (prominent) DarkBackground else TextPrimary,
            modifier = Modifier.size(if (size > 56.dp) 36.dp else 24.dp))
    }
}
