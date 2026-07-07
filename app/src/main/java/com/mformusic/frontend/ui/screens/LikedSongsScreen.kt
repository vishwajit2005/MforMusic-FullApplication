package com.mformusic.frontend.ui.screens

import androidx.compose.animation.core.animateDpAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.DragHandle
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.RemoveCircleOutline
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
import com.mformusic.frontend.model.SongResponse
import com.mformusic.frontend.ui.components.ShimmerSongRow
import com.mformusic.frontend.ui.theme.*
import com.mformusic.frontend.viewmodel.LikedSongsViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LikedSongsScreen(
    onBackClick: () -> Unit,
    viewModel: LikedSongsViewModel = viewModel()
) {
    val likedSongs by viewModel.likedSongs.collectAsStateWithLifecycle()
    val isLoading by viewModel.isLoading.collectAsStateWithLifecycle()
    val error by viewModel.error.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }

    // Drag-to-reorder state
    var draggedIndex by remember { mutableStateOf<Int?>(null) }
    var targetIndex by remember { mutableStateOf<Int?>(null) }

    LaunchedEffect(Unit) {
        viewModel.fetchLikedSongs()
    }

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
                title = { Text("Liked Songs", fontWeight = FontWeight.Bold, color = TextPrimary) },
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
            if (isLoading && likedSongs.isEmpty()) {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    item { PlaylistHeader(songCount = 0) }
                    items(5) { ShimmerSongRow() }
                }
            } else if (likedSongs.isEmpty()) {
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
                        "Songs you like will appear here",
                        color = TextPrimary,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        "Save songs by tapping the heart icon in the player",
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
                        PlaylistHeader(songCount = likedSongs.size)
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
                    itemsIndexed(likedSongs, key = { _, song -> song.externalTrackId }) { index, song ->
                        val isDragged = draggedIndex == index
                        val elevation by animateDpAsState(if (isDragged) 8.dp else 0.dp, label = "elevation")

                        LikedSongRow(
                            song = song,
                            isDragged = isDragged,
                            elevation = elevation,
                            onClick = { viewModel.playSong(song) },
                            onRemove = { viewModel.removeSong(song) },
                            onDragStart = { draggedIndex = index },
                            onDrag = { dragDeltaY, itemHeightPx ->
                                val currentDrag = draggedIndex ?: return@LikedSongRow
                                val offset = (dragDeltaY / itemHeightPx).toInt()
                                val newTarget = (currentDrag + offset).coerceIn(0, likedSongs.size - 1)
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
fun PlaylistHeader(songCount: Int) {
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
                            listOf(Color(0xFF450E4B), Color(0xFFC42D69), Color(0xFFE8D093))
                        )
                    ),
                contentAlignment = Alignment.Center
            ) {
                AsyncImage(
                    model = "https://misc.scdn.co/abab43419590204d3d330d7c8be0a55a6157a090.jpg",
                    contentDescription = null,
                    modifier = Modifier.fillMaxSize(),
                    contentScale = ContentScale.Crop
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
                    "Liked Songs",
                    fontSize = 24.sp,
                    fontWeight = FontWeight.ExtraBold,
                    color = TextPrimary
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    "$songCount ${if (songCount == 1) "song" else "songs"}",
                    fontSize = 14.sp,
                    color = TextSecondary
                )
            }
        }
    }
}

@Composable
fun LikedSongRow(
    song: SongResponse,
    isDragged: Boolean = false,
    elevation: androidx.compose.ui.unit.Dp = 0.dp,
    onClick: () -> Unit,
    onRemove: () -> Unit,
    onDragStart: () -> Unit = {},
    onDrag: (dragDeltaY: Float, itemHeightPx: Float) -> Unit = { _, _ -> },
    onDragEnd: () -> Unit = {}
) {
    var itemHeight by remember { mutableStateOf(0f) }
    var accumulatedDrag by remember { mutableStateOf(0f) }

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

        // Remove button
        IconButton(
            onClick = onRemove,
            modifier = Modifier.size(36.dp)
        ) {
            Icon(
                Icons.Default.RemoveCircleOutline,
                contentDescription = "Remove from liked",
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
                            // Reset accumulator after each index move
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
