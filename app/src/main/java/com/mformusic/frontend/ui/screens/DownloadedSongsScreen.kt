package com.mformusic.frontend.ui.screens

import androidx.compose.animation.core.animateDpAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.DragHandle
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import kotlin.math.abs
import com.mformusic.frontend.data.local.DownloadedSong
import com.mformusic.frontend.ui.components.ShimmerSongRow
import com.mformusic.frontend.ui.theme.*
import com.mformusic.frontend.viewmodel.DownloadedSongsViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DownloadedSongsScreen(
    onBackClick: () -> Unit,
    viewModel: DownloadedSongsViewModel = viewModel()
) {
    val downloadedSongs by viewModel.downloadedSongs.collectAsStateWithLifecycle()
    val isLoading by viewModel.isLoading.collectAsStateWithLifecycle()
    val error by viewModel.error.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }

    // Drag-to-reorder state
    var draggedIndex by remember { mutableStateOf<Int?>(null) }

    LaunchedEffect(error) {
        error?.let {
            snackbarHostState.showSnackbar(it)
            viewModel.clearError()
        }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
        containerColor = DarkBackground,
        topBar = {
            TopAppBar(
                title = { Text("Downloaded Songs", fontWeight = FontWeight.Bold, color = TextPrimary) },
                navigationIcon = {
                    IconButton(onClick = onBackClick) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back", tint = TextPrimary)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Color.Transparent
                )
            )
        }
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        listOf(GradientTop, GradientMid, DarkBackground),
                        endY = 800f
                    )
                )
                .padding(padding)
        ) {
            if (isLoading && downloadedSongs.isEmpty()) {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    item { DownloadedPlaylistHeader(songCount = 0) }
                    items(5) { ShimmerSongRow() }
                }
            } else if (downloadedSongs.isEmpty()) {
                Column(
                    modifier = Modifier.fillMaxSize(),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center
                ) {
                    Icon(
                        Icons.Default.MusicNote,
                        contentDescription = null,
                        tint = TextMuted,
                        modifier = Modifier.size(64.dp)
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    Text(
                        "No offline downloads yet",
                        color = TextPrimary,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        "Download songs to play them offline",
                        color = TextSecondary,
                        fontSize = 14.sp
                    )
                }
            } else {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    item {
                        DownloadedPlaylistHeader(songCount = downloadedSongs.size)
                    }
                    // Drag hint label
                    item {
                        Text(
                            "Long-press ☰ and drag to reorder",
                            fontSize = 11.sp,
                            color = TextMuted,
                            modifier = Modifier.padding(start = 4.dp, bottom = 4.dp)
                        )
                    }
                    itemsIndexed(downloadedSongs, key = { _, song -> song.externalTrackId }) { index, song ->
                        val isDragged = draggedIndex == index
                        val elevation by animateDpAsState(if (isDragged) 8.dp else 0.dp, label = "elevation")

                        DownloadedSongRow(
                            song = song,
                            isDragged = isDragged,
                            elevation = elevation,
                            onClick = { viewModel.playSong(song) },
                            onDelete = { viewModel.deleteSong(song) },
                            onDragStart = { draggedIndex = index },
                            onDrag = { dragDeltaY, itemHeightPx ->
                                val currentDrag = draggedIndex ?: return@DownloadedSongRow
                                val offset = (dragDeltaY / itemHeightPx).toInt()
                                val newTarget = (currentDrag + offset).coerceIn(0, downloadedSongs.size - 1)
                                if (newTarget != currentDrag) {
                                    viewModel.reorderSongs(currentDrag, newTarget)
                                    draggedIndex = newTarget
                                }
                            },
                            onDragEnd = { draggedIndex = null }
                        )
                    }
                    item {
                        Spacer(modifier = Modifier.height(24.dp))
                    }
                }
            }
        }
    }
}

@Composable
fun DownloadedPlaylistHeader(songCount: Int) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 16.dp)
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(120.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(
                        Brush.linearGradient(
                            listOf(Color(0xFF0F5A47), Color(0xFF1DB954), Color(0xFF88ED9C))
                        )
                    ),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    Icons.Default.MusicNote,
                    contentDescription = null,
                    tint = Color.White,
                    modifier = Modifier.size(48.dp)
                )
            }
            Spacer(modifier = Modifier.width(16.dp))
            Column {
                Text(
                    "Playlist",
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                    color = TextPrimary
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    "Downloads",
                    fontSize = 24.sp,
                    fontWeight = FontWeight.ExtraBold,
                    color = TextPrimary
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    "$songCount ${if (songCount == 1) "song" else "songs"} • Available Offline",
                    fontSize = 14.sp,
                    color = TextSecondary
                )
            }
        }
    }
}

@Composable
fun DownloadedSongRow(
    song: DownloadedSong,
    isDragged: Boolean = false,
    elevation: androidx.compose.ui.unit.Dp = 0.dp,
    onClick: () -> Unit,
    onDelete: () -> Unit,
    onDragStart: () -> Unit = {},
    onDrag: (dragDeltaY: Float, itemHeightPx: Float) -> Unit = { _, _ -> },
    onDragEnd: () -> Unit = {}
) {
    var itemHeight by remember { mutableStateOf(0f) }
    var accumulatedDrag by remember { mutableStateOf(0f) }

    // Confirm delete dialog
    var showDeleteDialog by remember { mutableStateOf(false) }

    if (showDeleteDialog) {
        AlertDialog(
            onDismissRequest = { showDeleteDialog = false },
            title = { Text("Remove Download", color = TextPrimary) },
            text = {
                Text(
                    "Remove \"${song.title}\" from downloads?",
                    color = TextSecondary
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    showDeleteDialog = false
                    onDelete()
                }) {
                    Text("Remove", color = ErrorRed)
                }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteDialog = false }) {
                    Text("Cancel", color = TextSecondary)
                }
            },
            containerColor = DarkCard
        )
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .shadow(elevation, RoundedCornerShape(8.dp))
            .clip(RoundedCornerShape(8.dp))
            .background(if (isDragged) DarkCardElevated else Color.Transparent)
            .clickable { onClick() }
            .padding(vertical = 8.dp, horizontal = 4.dp)
            .onGloballyPositioned { layoutCoords -> itemHeight = layoutCoords.size.height.toFloat() },
        verticalAlignment = Alignment.CenterVertically
    ) {
        // Album Art
        Box(
            modifier = Modifier
                .size(56.dp)
                .clip(RoundedCornerShape(4.dp))
                .background(DarkCard)
        ) {
            if (!song.thumbnailUrl.isNullOrBlank()) {
                AsyncImage(
                    model = song.thumbnailUrl,
                    contentDescription = null,
                    modifier = Modifier.fillMaxSize(),
                    contentScale = ContentScale.Crop
                )
            } else {
                Icon(
                    Icons.Default.MusicNote,
                    contentDescription = null,
                    tint = TextSecondary,
                    modifier = Modifier.align(Alignment.Center)
                )
            }
        }
        Spacer(modifier = Modifier.width(14.dp))

        // Title + Artist
        Column(modifier = Modifier.weight(1f)) {
            Text(
                song.title,
                color = TextPrimary,
                fontWeight = FontWeight.SemiBold,
                fontSize = 15.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            Text(
                song.artistName ?: "Unknown Artist",
                color = TextSecondary,
                fontSize = 13.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }

        // Delete button (shows confirmation dialog)
        IconButton(
            onClick = { showDeleteDialog = true },
            modifier = Modifier.size(36.dp)
        ) {
            Icon(
                Icons.Default.Delete,
                contentDescription = "Delete download",
                tint = ErrorRed,
                modifier = Modifier.size(20.dp)
            )
        }

        // Drag handle — long-press and drag to reorder
        Icon(
            Icons.Default.DragHandle,
            contentDescription = "Drag to reorder",
            tint = TextMuted,
            modifier = Modifier
                .size(24.dp)
                .pointerInput(Unit) {
                    detectDragGesturesAfterLongPress(
                        onDragStart = {
                            accumulatedDrag = 0f
                            onDragStart()
                        },
                        onDrag = { change, dragAmount ->
                            change.consume()
                            accumulatedDrag += dragAmount.y
                            val h = if (itemHeight > 0) itemHeight else 1f
                            onDrag(accumulatedDrag, h)
                            if (abs(accumulatedDrag) >= h) {
                                accumulatedDrag = 0f
                            }
                        },
                        onDragEnd = {
                            accumulatedDrag = 0f
                            onDragEnd()
                        },
                        onDragCancel = {
                            accumulatedDrag = 0f
                            onDragEnd()
                        }
                    )
                }
        )
    }
}
