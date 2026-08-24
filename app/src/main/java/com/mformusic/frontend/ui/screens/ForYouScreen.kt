package com.mformusic.frontend.ui.screens

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import com.mformusic.frontend.model.SongResponse
import com.mformusic.frontend.ui.components.ShimmerSongRow
import com.mformusic.frontend.ui.theme.*
import com.mformusic.frontend.viewmodel.ForYouUiState
import com.mformusic.frontend.viewmodel.ForYouViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ForYouScreen(
    forYouViewModel: ForYouViewModel = viewModel()
) {
    val uiState by forYouViewModel.uiState.collectAsStateWithLifecycle()
    val isRefreshing by forYouViewModel.isRefreshing.collectAsStateWithLifecycle()

    PullToRefreshBox(
        isRefreshing = isRefreshing,
        onRefresh = { forYouViewModel.fetchRecommendations() },
        modifier = Modifier.fillMaxSize()
    ) {
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        colorStops = arrayOf(
                            0.0f to Color(0xFF0D1B2A),
                            0.35f to Color(0xFF1A1A2E),
                            1.0f to DarkBackground
                        )
                    )
                ),
            verticalArrangement = Arrangement.spacedBy(0.dp)
        ) {
            // ── Hero Header ──────────────────────────────────────────────────────
            item {
                ForYouHeroHeader()
            }

            // ── Content ──────────────────────────────────────────────────────────
            when (val state = uiState) {
                is ForYouUiState.Loading -> {
                    items(8) {
                        ShimmerSongRow()
                    }
                }

                is ForYouUiState.Error -> {
                    item {
                        ForYouErrorState(
                            message = state.message,
                            onRetry = { forYouViewModel.fetchRecommendations() }
                        )
                    }
                }

                is ForYouUiState.Success -> {
                    if (state.songs.isEmpty()) {
                        item { ForYouColdStartState() }
                    } else {
                        // Source badge
                        item {
                            Text(
                                text = "Picked just for you · ${state.songs.size} tracks",
                                color = TextSecondary,
                                fontSize = 13.sp,
                                modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp)
                            )
                        }
                        itemsIndexed(state.songs) { index, song ->
                            ForYouSongRow(
                                song = song,
                                rank = index + 1,
                                onClick = { forYouViewModel.playSong(song) }
                            )
                        }
                        item { Spacer(modifier = Modifier.height(16.dp)) }
                    }
                }
            }
        }
    }
}

// ── Hero Header ────────────────────────────────────────────────────────────────
@Composable
private fun ForYouHeroHeader() {
    // Infinite pulse animation for the sparkle icon
    val infiniteTransition = rememberInfiniteTransition(label = "hero_pulse")
    val iconScale by infiniteTransition.animateFloat(
        initialValue = 1f,
        targetValue = 1.15f,
        animationSpec = infiniteRepeatable(
            animation = tween(1200, easing = EaseInOutSine),
            repeatMode = RepeatMode.Reverse
        ),
        label = "icon_scale"
    )

    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(200.dp)
            .background(
                Brush.radialGradient(
                    colors = listOf(Color(0xFF1DB954).copy(alpha = 0.25f), Color.Transparent),
                    radius = 600f
                )
            ),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(
                imageVector = Icons.Default.AutoAwesome,
                contentDescription = null,
                tint = SpotifyGreen,
                modifier = Modifier
                    .size(48.dp)
                    .scale(iconScale)
            )
            Spacer(modifier = Modifier.height(12.dp))
            Text(
                text = "For You",
                fontSize = 34.sp,
                fontWeight = FontWeight.ExtraBold,
                color = TextPrimary
            )
            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = "Personalised picks, updated as you listen",
                fontSize = 14.sp,
                color = TextSecondary
            )
        }
    }
}

// ── Song Row ───────────────────────────────────────────────────────────────────
@Composable
private fun ForYouSongRow(
    song: SongResponse,
    rank: Int,
    onClick: () -> Unit
) {
    var isPressed by remember { mutableStateOf(false) }
    val bgColor by animateColorAsState(
        targetValue = if (isPressed) DarkCardElevated else Color.Transparent,
        animationSpec = tween(100),
        label = "row_bg"
    )

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(bgColor)
            .clickable {
                isPressed = true
                onClick()
            }
            .padding(horizontal = 20.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // Rank number
        Text(
            text = rank.toString().padStart(2, '0'),
            color = if (rank <= 3) SpotifyGreen else TextMuted,
            fontSize = 13.sp,
            fontWeight = if (rank <= 3) FontWeight.Bold else FontWeight.Normal,
            modifier = Modifier.width(28.dp)
        )

        Spacer(modifier = Modifier.width(12.dp))

        // Album art
        Box(
            modifier = Modifier
                .size(52.dp)
                .clip(RoundedCornerShape(6.dp))
                .background(DarkCard),
            contentAlignment = Alignment.Center
        ) {
            if (!song.thumbnailUrl.isNullOrBlank()) {
                AsyncImage(
                    model = song.thumbnailUrl,
                    contentDescription = null,
                    modifier = Modifier.fillMaxSize(),
                    contentScale = ContentScale.Crop
                )
            } else {
                Icon(Icons.Default.MusicNote, contentDescription = null, tint = TextSecondary)
            }
        }

        Spacer(modifier = Modifier.width(14.dp))

        // Title + artist
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = song.title,
                color = TextPrimary,
                fontWeight = FontWeight.SemiBold,
                fontSize = 15.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            Text(
                text = song.artistName ?: "Unknown Artist",
                color = TextSecondary,
                fontSize = 13.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }

        // Liked indicator
        if (song.liked) {
            Icon(
                Icons.Default.Favorite,
                contentDescription = "Liked",
                tint = SpotifyGreen,
                modifier = Modifier.size(18.dp)
            )
            Spacer(modifier = Modifier.width(8.dp))
        }

        // Play button
        Icon(
            Icons.Default.PlayArrow,
            contentDescription = "Play",
            tint = TextMuted,
            modifier = Modifier.size(22.dp)
        )
    }

    // Thin divider between rows
    HorizontalDivider(
        modifier = Modifier.padding(start = 72.dp, end = 20.dp),
        thickness = 0.5.dp,
        color = DarkCard
    )

    // Reset press state
    LaunchedEffect(isPressed) {
        if (isPressed) {
            kotlinx.coroutines.delay(150)
            isPressed = false
        }
    }
}

// ── Empty / Cold-start state ───────────────────────────────────────────────────
@Composable
private fun ForYouColdStartState() {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 32.dp, vertical = 48.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Icon(
            Icons.Default.AutoAwesome,
            contentDescription = null,
            tint = TextMuted,
            modifier = Modifier.size(56.dp)
        )
        Spacer(modifier = Modifier.height(16.dp))
        Text(
            "Building your taste profile",
            fontSize = 18.sp,
            fontWeight = FontWeight.Bold,
            color = TextPrimary
        )
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            "Listen to a few more songs and we'll personalise this feed just for you.",
            fontSize = 14.sp,
            color = TextSecondary,
            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            lineHeight = 20.sp
        )
    }
}

// ── Error state ────────────────────────────────────────────────────────────────
@Composable
private fun ForYouErrorState(message: String, onRetry: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 32.dp, vertical = 48.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Icon(
            Icons.Default.WifiOff,
            contentDescription = null,
            tint = TextMuted,
            modifier = Modifier.size(48.dp)
        )
        Spacer(modifier = Modifier.height(16.dp))
        Text(message, fontSize = 15.sp, color = TextSecondary,
            textAlign = androidx.compose.ui.text.style.TextAlign.Center)
        Spacer(modifier = Modifier.height(20.dp))
        OutlinedButton(
            onClick = onRetry,
            colors = ButtonDefaults.outlinedButtonColors(contentColor = SpotifyGreen),
            border = androidx.compose.foundation.BorderStroke(1.dp, SpotifyGreen)
        ) {
            Icon(Icons.Default.Refresh, contentDescription = null, modifier = Modifier.size(16.dp))
            Spacer(modifier = Modifier.width(6.dp))
            Text("Retry", fontWeight = FontWeight.SemiBold)
        }
    }
}
