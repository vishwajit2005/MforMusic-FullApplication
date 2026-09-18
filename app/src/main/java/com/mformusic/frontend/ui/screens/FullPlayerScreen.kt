package com.mformusic.frontend.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.text.style.TextOverflow
import com.mformusic.frontend.ui.components.AlbumArtwork
import com.mformusic.frontend.ui.components.PlaybackButton
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

    val similar by playerViewModel.similarSongs.collectAsStateWithLifecycle()
    var showSimilar by remember { mutableStateOf(false) }
    LaunchedEffect(showSimilar, currentTrack?.externalTrackId) {
        if (showSimilar && currentTrack != null) playerViewModel.loadSimilarSongs()
    }

    var showMenu by remember { mutableStateOf(false) }
    val progress = if (duration > 0) position.toFloat() / duration.toFloat() else 0f

    BoxWithConstraints(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    listOf(
                        GradientTop,
                        DarkBackground,
                        DarkBackground
                    )
                )
            )
    ) {
        val artworkSize = (maxHeight - 490.dp).coerceIn(160.dp, 380.dp)
        Column(
            modifier = Modifier
                .fillMaxSize()
                .systemBarsPadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp),
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
                Box {
                    IconButton(onClick = { showMenu = true }) {
                        Icon(Icons.Default.MoreVert, contentDescription = "Track options", tint = TextPrimary)
                    }
                    DropdownMenu(expanded = showMenu, onDismissRequest = { showMenu = false }) {
                        DropdownMenuItem(text = { Text(if (currentTrack?.liked == true) "Remove from liked songs" else "Like song") },
                            enabled = currentTrack?.id != null,
                            onClick = { showMenu = false; playerViewModel.toggleLike() })
                        DropdownMenuItem(text = { Text(if (isDownloaded) "Remove download" else "Download song") },
                            enabled = currentTrack != null && !isDownloading,
                            onClick = { showMenu = false; playerViewModel.toggleDownload() })
                        DropdownMenuItem(text = { Text("Close player") },
                            onClick = { showMenu = false; onDismiss() })
                    }
                }
            }

            Spacer(modifier = Modifier.height(20.dp))

            AlbumArtwork(albumArt, Modifier.size(artworkSize))

            Spacer(modifier = Modifier.height(16.dp))

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
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    Text(
                        text = artist ?: "Unknown Artist",
                        fontSize = 16.sp,
                        color = TextSecondary,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
                Row(
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    IconButton(
                        onClick = { playerViewModel.toggleDownload() },
                        enabled = currentTrack != null && !isDownloading
                    ) {
                        when {
                            isDownloading -> {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(24.dp),
                                    color = Accent,
                                    strokeWidth = 2.dp
                                )
                            }
                            isDownloaded -> {
                                Icon(
                                    imageVector = Icons.Default.CheckCircle,
                                    contentDescription = "Downloaded",
                                    tint = Accent,
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

                    IconButton(onClick = { playerViewModel.toggleLike() }, enabled = currentTrack?.id != null) {
                        val isLiked = currentTrack?.liked == true
                        Icon(
                            imageVector = if (isLiked) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                            contentDescription = if (isLiked) "Unlike" else "Like",
                            tint = if (isLiked) Accent else TextSecondary,
                            modifier = Modifier.size(28.dp)
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Seek Bar
            Slider(
                value = progress.coerceIn(0f, 1f),
                enabled = duration > 0,
                onValueChange = { newVal ->
                    if (duration > 0) {
                        playerViewModel.seekTo((newVal * duration).toLong())
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                colors = SliderDefaults.colors(
                    thumbColor = TextPrimary,
                    activeTrackColor = Accent,
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

            Spacer(modifier = Modifier.height(16.dp))

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
                        contentDescription = if (isShuffleOn) "Turn shuffle off" else "Turn shuffle on",
                        tint = if (isShuffleOn) Accent else TextSecondary
                    )
                }

                PlaybackButton(Icons.Default.SkipPrevious, "Previous", { playerViewModel.skipToPrevious() })
                PlaybackButton(if (isPlaying) Icons.Default.Pause else Icons.Default.PlayArrow,
                    if (isPlaying) "Pause" else "Play", { playerViewModel.togglePlayPause() },
                    prominent = true, size = 72.dp)
                PlaybackButton(Icons.Default.SkipNext, "Next", { playerViewModel.skipToNext() })

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
                            tint = Accent
                        )
                        PlayerManager.RepeatMode.ONE -> Icon(
                            Icons.Default.RepeatOne,
                            contentDescription = "Repeat One",
                            tint = Accent
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(20.dp))
            OutlinedButton(
                onClick = { showSimilar = !showSimilar },
                enabled = currentTrack != null,
                modifier = Modifier.fillMaxWidth()
            ) {
                Icon(Icons.Default.QueueMusic, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text(if (showSimilar) "Hide similar songs" else "Similar songs")
            }
            if (showSimilar) {
                Text("Inspired by this song and your recent listening", color = TextSecondary,
                    fontSize = 13.sp, modifier = Modifier.padding(vertical = 12.dp))
                when {
                    similar.loading -> CircularProgressIndicator(
                        color = Accent, modifier = Modifier.padding(16.dp))
                    similar.error != null -> {
                        Text(similar.error ?: "Please try again", color = TextSecondary)
                        TextButton(onClick = playerViewModel::loadSimilarSongs) { Text("Retry") }
                    }
                    similar.songs.isEmpty() -> Text(
                        "No similar songs yet. Try another song as the catalog grows.",
                        color = TextSecondary, modifier = Modifier.padding(vertical = 16.dp))
                }
                similar.songs.forEach { song ->
                    Surface(
                        onClick = { playerViewModel.playSimilarSong(song) },
                        enabled = similar.playingId == null,
                        color = DarkCardElevated, shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)
                    ) {
                        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                            AlbumArtwork(song.thumbnailUrl, Modifier.size(48.dp))
                            Spacer(Modifier.width(12.dp))
                            Column(Modifier.weight(1f)) {
                                Text(song.title, color = TextPrimary, fontWeight = FontWeight.SemiBold,
                                    maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Text(song.artistName ?: "Unknown artist", color = TextSecondary,
                                    maxLines = 1, overflow = TextOverflow.Ellipsis, fontSize = 12.sp)
                            }
                            if (similar.playingId == song.externalTrackId) {
                                CircularProgressIndicator(Modifier.size(24.dp), color = Accent, strokeWidth = 2.dp)
                            } else Icon(Icons.Default.PlayArrow, "Play ${song.title}", tint = Accent)
                        }
                    }
                }
            }
            Spacer(modifier = Modifier.height(24.dp))
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
