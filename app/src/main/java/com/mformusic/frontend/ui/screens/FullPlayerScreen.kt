package com.mformusic.frontend.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import com.mformusic.frontend.network.PlayerManager
import com.mformusic.frontend.ui.theme.*
import com.mformusic.frontend.viewmodel.PlayerViewModel

@Composable
fun FullPlayerScreen(
    playerViewModel: PlayerViewModel = viewModel(),
    onDismiss: () -> Unit
) {
    val isPlaying by playerViewModel.isPlaying.collectAsStateWithLifecycle()
    val currentTrack by playerViewModel.currentTrack.collectAsStateWithLifecycle()
    val title by playerViewModel.currentTrackTitle.collectAsStateWithLifecycle()
    val artist by playerViewModel.currentArtistName.collectAsStateWithLifecycle()
    val albumArt by playerViewModel.currentAlbumArt.collectAsStateWithLifecycle()
    val position by playerViewModel.currentPosition.collectAsStateWithLifecycle()
    val duration by playerViewModel.duration.collectAsStateWithLifecycle()
    val isDownloaded by playerViewModel.isDownloaded.collectAsStateWithLifecycle()
    val isDownloading by playerViewModel.isDownloading.collectAsStateWithLifecycle()
    val isShuffleOn by playerViewModel.isShuffleOn.collectAsStateWithLifecycle()
    val repeatMode by playerViewModel.repeatMode.collectAsStateWithLifecycle()

    val progress = if (duration > 0) position.toFloat() / duration.toFloat() else 0f

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    listOf(
                        Color(0xFF2A3A2E),
                        DarkBackground,
                        DarkBackground
                    )
                )
            )
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 32.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            // Drag handle
            Spacer(modifier = Modifier.height(16.dp))
            Box(
                modifier = Modifier
                    .width(40.dp)
                    .height(4.dp)
                    .clip(CircleShape)
                    .background(TextMuted)
            )
            Spacer(modifier = Modifier.height(16.dp))

            // Top bar
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconButton(onClick = onDismiss) {
                    Icon(
                        Icons.Default.KeyboardArrowDown,
                        contentDescription = "Collapse",
                        tint = TextPrimary,
                        modifier = Modifier.size(32.dp)
                    )
                }
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("NOW PLAYING", fontSize = 11.sp, color = TextSecondary, letterSpacing = 2.sp)
                }
                IconButton(onClick = { /* TODO: add to queue */ }) {
                    Icon(Icons.Default.MoreVert, contentDescription = "More", tint = TextPrimary)
                }
            }

            Spacer(modifier = Modifier.height(32.dp))

            // Album Art
            Box(
                modifier = Modifier
                    .size(300.dp)
                    .clip(RoundedCornerShape(16.dp))
                    .background(DarkCard),
                contentAlignment = Alignment.Center
            ) {
                if (albumArt != null) {
                    AsyncImage(
                        model = albumArt,
                        contentDescription = "Album Art",
                        modifier = Modifier.fillMaxSize(),
                        contentScale = ContentScale.Crop
                    )
                } else {
                    Icon(
                        Icons.Default.MusicNote,
                        contentDescription = null,
                        tint = TextSecondary,
                        modifier = Modifier.size(80.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(40.dp))

            // Song Info
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = title ?: "Nothing Playing",
                        fontSize = 22.sp,
                        fontWeight = FontWeight.Bold,
                        color = TextPrimary,
                        maxLines = 1
                    )
                    Text(
                        text = artist ?: "Unknown Artist",
                        fontSize = 16.sp,
                        color = TextSecondary,
                        maxLines = 1
                    )
                }
                Row(
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    IconButton(
                        onClick = { playerViewModel.toggleDownload() },
                        enabled = currentTrack != null
                    ) {
                        when {
                            isDownloading -> {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(24.dp),
                                    color = SpotifyGreen,
                                    strokeWidth = 2.dp
                                )
                            }
                            isDownloaded -> {
                                Icon(
                                    imageVector = Icons.Default.CheckCircle,
                                    contentDescription = "Downloaded",
                                    tint = SpotifyGreen,
                                    modifier = Modifier.size(28.dp)
                                )
                            }
                            else -> {
                                Icon(
                                    imageVector = Icons.Default.DownloadForOffline,
                                    contentDescription = "Download",
                                    tint = TextSecondary,
                                    modifier = Modifier.size(28.dp)
                                )
                            }
                        }
                    }

                    Spacer(modifier = Modifier.width(8.dp))

                    IconButton(onClick = { playerViewModel.toggleLike() }) {
                        val isLiked = currentTrack?.liked == true
                        Icon(
                            imageVector = if (isLiked) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                            contentDescription = if (isLiked) "Unlike" else "Like",
                            tint = if (isLiked) SpotifyGreen else TextSecondary,
                            modifier = Modifier.size(28.dp)
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Seek Bar
            Slider(
                value = progress,
                onValueChange = { newVal ->
                    if (duration > 0) {
                        playerViewModel.seekTo((newVal * duration).toLong())
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                colors = SliderDefaults.colors(
                    thumbColor = TextPrimary,
                    activeTrackColor = SpotifyGreen,
                    inactiveTrackColor = DarkCardElevated
                )
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(formatTime(position), fontSize = 12.sp, color = TextSecondary)
                Text(formatTime(duration), fontSize = 12.sp, color = TextSecondary)
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Playback Controls
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly,
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Shuffle
                IconButton(
                    onClick = { playerViewModel.toggleShuffle() },
                    modifier = Modifier.size(48.dp)
                ) {
                    Icon(
                        Icons.Default.Shuffle,
                        contentDescription = "Shuffle",
                        tint = if (isShuffleOn) SpotifyGreen else TextSecondary
                    )
                }

                // Skip Previous
                IconButton(
                    onClick = { playerViewModel.skipToPrevious() },
                    modifier = Modifier.size(56.dp)
                ) {
                    Icon(
                        Icons.Default.SkipPrevious,
                        contentDescription = "Previous",
                        tint = TextPrimary,
                        modifier = Modifier.size(40.dp)
                    )
                }

                // Play/Pause — large button
                IconButton(
                    onClick = { playerViewModel.togglePlayPause() },
                    modifier = Modifier
                        .size(72.dp)
                        .clip(CircleShape)
                        .background(SpotifyGreen)
                ) {
                    Icon(
                        if (isPlaying) Icons.Default.Pause else Icons.Default.PlayArrow,
                        contentDescription = if (isPlaying) "Pause" else "Play",
                        tint = Color.Black,
                        modifier = Modifier.size(40.dp)
                    )
                }

                // Skip Next
                IconButton(
                    onClick = { playerViewModel.skipToNext() },
                    modifier = Modifier.size(56.dp)
                ) {
                    Icon(
                        Icons.Default.SkipNext,
                        contentDescription = "Next",
                        tint = TextPrimary,
                        modifier = Modifier.size(40.dp)
                    )
                }

                // Repeat (cycles OFF → ALL → ONE)
                IconButton(
                    onClick = { playerViewModel.cycleRepeatMode() },
                    modifier = Modifier.size(48.dp)
                ) {
                    when (repeatMode) {
                        PlayerManager.RepeatMode.OFF -> Icon(
                            Icons.Default.Repeat,
                            contentDescription = "Repeat Off",
                            tint = TextSecondary
                        )
                        PlayerManager.RepeatMode.ALL -> Icon(
                            Icons.Default.Repeat,
                            contentDescription = "Repeat All",
                            tint = SpotifyGreen
                        )
                        PlayerManager.RepeatMode.ONE -> Icon(
                            Icons.Default.RepeatOne,
                            contentDescription = "Repeat One",
                            tint = SpotifyGreen
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(32.dp))
        }
    }
}

private fun formatTime(ms: Long): String {
    if (ms <= 0) return "0:00"
    val totalSeconds = ms / 1000
    val minutes = totalSeconds / 60
    val seconds = totalSeconds % 60
    return "$minutes:${seconds.toString().padStart(2, '0')}"
}
