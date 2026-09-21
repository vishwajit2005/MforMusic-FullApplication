package com.mformusic.frontend.ui.screens

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.LiveRegionMode
import com.mformusic.frontend.ui.components.AlbumArtwork
import com.mformusic.frontend.viewmodel.PlayerViewModel
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
    onExplore: () -> Unit,
    forYouViewModel: ForYouViewModel = viewModel(),
    playerViewModel: PlayerViewModel = viewModel()
) {
    val currentTrack by playerViewModel.currentTrack.collectAsStateWithLifecycle()
    val isPlaying by playerViewModel.isPlaying.collectAsStateWithLifecycle()
    val uiState by forYouViewModel.uiState.collectAsStateWithLifecycle()
    val waitingForService by forYouViewModel.waitingForService.collectAsStateWithLifecycle()
    val isRefreshing by forYouViewModel.isRefreshing.collectAsStateWithLifecycle()

    PullToRefreshBox(
        isRefreshing = isRefreshing,
        onRefresh = { forYouViewModel.fetchRecommendations() },
        modifier = Modifier.fillMaxSize()
    ) {
        AnimatedContent(targetState = uiState, contentKey = { it::class }, label = "feed_state",
            transitionSpec = { fadeIn(tween(240)) togetherWith fadeOut(tween(120)) }) { displayedState ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        colorStops = arrayOf(
                            0.0f to GradientTop,
                            0.35f to GradientMid,
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
            when (val state = displayedState) {
                is ForYouUiState.Loading -> {
                    item {
                        Text(if (waitingForService) "Recommendations are waking up. Retrying automatically…" else "Finding your next favourite…", color = TextSecondary,
                            modifier = Modifier.padding(20.dp).semantics { liveRegion = LiveRegionMode.Polite })
                    }
                    items(6) {
                        Box(Modifier.padding(horizontal = 20.dp)) { ShimmerSongRow() }
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
                        item { ForYouColdStartState(onExplore) }
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
                        itemsIndexed(state.songs, key = { index, song -> "${song.externalTrackId}_$index" }) { index, song ->
                            ForYouSongRow(
                                song = song,
                                rank = index + 1,
                                isCurrent = currentTrack?.externalTrackId == song.externalTrackId,
                                isPlaying = isPlaying,
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
                    colors = listOf(Accent.copy(alpha = 0.16f), Color.Transparent),
                    radius = 600f
                )
            ),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(
                imageVector = Icons.Default.AutoAwesome,
                contentDescription = null,
                tint = Accent,
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
    isCurrent: Boolean,
    isPlaying: Boolean,
    onClick: () -> Unit
) {
    val interaction = remember { MutableInteractionSource() }
    val isPressed by interaction.collectIsPressedAsState()
    val scale by animateFloatAsState(if (isPressed) 0.98f else 1f, label = "recommendation_press")
    val bgColor by animateColorAsState(
        targetValue = if (isPressed) DarkCardElevated else if (isCurrent) Accent.copy(alpha = 0.12f) else DarkSurface,
        animationSpec = tween(100),
        label = "row_bg"
    )

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 4.dp)
            .scale(scale)
            .clip(RoundedCornerShape(18.dp))
            .background(bgColor)
            .clickable(interactionSource = interaction, indication = ripple(),
                onClickLabel = "Play ${song.title}", onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // Rank number
        Text(
            text = rank.toString().padStart(2, '0'),
            color = if (rank <= 3) Accent else TextMuted,
            fontSize = 13.sp,
            fontWeight = if (rank <= 3) FontWeight.Bold else FontWeight.Normal,
            modifier = Modifier.width(28.dp)
        )

        Spacer(modifier = Modifier.width(12.dp))

        AlbumArtwork(song.thumbnailUrl, Modifier.size(64.dp))

        Spacer(modifier = Modifier.width(14.dp))

        // Title + artist
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = song.title,
                color = if (isCurrent) Accent else TextPrimary,
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
                tint = Accent,
                modifier = Modifier.size(18.dp)
            )
            Spacer(modifier = Modifier.width(8.dp))
        }

        // Play button
        Icon(
            if (isCurrent && isPlaying) Icons.Default.GraphicEq else Icons.Default.PlayArrow,
            contentDescription = if (isCurrent && isPlaying) "Now playing" else null,
            tint = if (isCurrent) Accent else TextSecondary,
            modifier = Modifier.size(22.dp)
        )
    }

}

// ── Empty / Cold-start state ───────────────────────────────────────────────────
@Composable
private fun ForYouColdStartState(onExplore: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(20.dp)
            .clip(RoundedCornerShape(24.dp))
            .background(DarkCard)
            .padding(horizontal = 24.dp, vertical = 32.dp)
            .animateContentSize(),
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
        Spacer(Modifier.height(24.dp))
        Button(onClick = onExplore, modifier = Modifier.heightIn(min = 48.dp)) {
            Icon(Icons.Default.Search, null)
            Spacer(Modifier.width(8.dp))
            Text("Explore music")
        }
    }
}

// ── Error state ────────────────────────────────────────────────────────────────
@Composable
private fun ForYouErrorState(message: String, onRetry: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(20.dp)
            .clip(RoundedCornerShape(24.dp))
            .background(DarkCard)
            .padding(horizontal = 24.dp, vertical = 32.dp)
            .animateContentSize(),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Icon(
            Icons.Default.WifiOff,
            contentDescription = null,
            tint = TextMuted,
            modifier = Modifier.size(48.dp)
        )
        Spacer(modifier = Modifier.height(16.dp))
        Text("Let’s reconnect", style = MaterialTheme.typography.titleLarge, color = TextPrimary)
        Spacer(Modifier.height(8.dp))
        Text(message, modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }, fontSize = 15.sp, color = TextSecondary,
            textAlign = androidx.compose.ui.text.style.TextAlign.Center)
        Spacer(modifier = Modifier.height(20.dp))
        OutlinedButton(
            onClick = onRetry,
            colors = ButtonDefaults.outlinedButtonColors(contentColor = Accent),
            border = androidx.compose.foundation.BorderStroke(1.dp, Accent)
        ) {
            Icon(Icons.Default.Refresh, contentDescription = null, modifier = Modifier.size(16.dp))
            Spacer(modifier = Modifier.width(6.dp))
            Text("Retry", fontWeight = FontWeight.SemiBold)
        }
    }
}
