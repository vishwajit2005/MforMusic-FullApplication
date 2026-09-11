package com.mformusic.frontend.ui.screens

import androidx.compose.animation.*
import androidx.compose.animation.core.tween
import androidx.activity.compose.BackHandler
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.automirrored.filled.Logout
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
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import coil.compose.AsyncImage
import com.mformusic.frontend.data.TokenDataStore
import com.mformusic.frontend.model.SongResponse
import com.mformusic.frontend.navigation.Screen
import com.mformusic.frontend.navigation.bottomNavItems
import com.mformusic.frontend.ui.components.*
import com.mformusic.frontend.ui.theme.*
import com.mformusic.frontend.viewmodel.HomeViewModel
import com.mformusic.frontend.viewmodel.PlayerViewModel
import com.mformusic.frontend.viewmodel.SearchViewModel
import com.mformusic.frontend.ui.screens.ForYouScreen
import java.util.Calendar
import kotlinx.coroutines.launch

@Composable
fun MainAppScreen(tokenDataStore: TokenDataStore, onLogout: () -> Unit) {
    val navController = rememberNavController()
    val playerViewModel: PlayerViewModel = viewModel()

    val currentTrackTitle by playerViewModel.currentTrackTitle.collectAsStateWithLifecycle()
    val isPlaying by playerViewModel.isPlaying.collectAsStateWithLifecycle()
    val artist by playerViewModel.currentArtistName.collectAsStateWithLifecycle()
    val albumArt by playerViewModel.currentAlbumArt.collectAsStateWithLifecycle()
    val position by playerViewModel.currentPosition.collectAsStateWithLifecycle()
    val duration by playerViewModel.duration.collectAsStateWithLifecycle()

    var showFullPlayer by rememberSaveable { mutableStateOf(false) }

    Box(Modifier.fillMaxSize()) {
        Scaffold(
            modifier = if (showFullPlayer) Modifier.clearAndSetSemantics { } else Modifier,
            bottomBar = {
                Column(modifier = Modifier.background(Color.Transparent)) {
                    // Mini Player
                    AnimatedVisibility(visible = currentTrackTitle != null) {
                        MiniPlayer(
                            title = currentTrackTitle ?: "",
                            albumArt = albumArt,
                            artist = artist,
                            onPrevious = { playerViewModel.skipToPrevious() },
                            onNext = { playerViewModel.skipToNext() },
                            isPlaying = isPlaying,
                            progress = if (duration > 0) position.toFloat() / duration.toFloat() else 0f,
                            onTogglePlay = { playerViewModel.togglePlayPause() },
                            onExpand = { showFullPlayer = true }
                        )
                    }

                    // Bottom Navigation Bar
                    NavigationBar(
                        containerColor = DarkOverlay,
                        tonalElevation = 0.dp
                    ) {
                        val navBackStackEntry by navController.currentBackStackEntryAsState()
                        val currentRoute = navBackStackEntry?.destination?.route

                        bottomNavItems.forEach { screen ->
                            NavigationBarItem(
                                icon = { Icon(screen.icon!!, contentDescription = null, modifier = Modifier.size(24.dp)) },
                                label = { Text(screen.title, fontSize = 11.sp) },
                                selected = currentRoute == screen.route,
                                colors = NavigationBarItemDefaults.colors(
                                    selectedIconColor = Accent,
                                    selectedTextColor = Accent,
                                    unselectedIconColor = TextSecondary,
                                    unselectedTextColor = TextSecondary,
                                    indicatorColor = Accent.copy(alpha = 0.14f)
                                ),
                                onClick = {
                                    if (currentRoute != screen.route) {
                                        navController.navigate(screen.route) {
                                            popUpTo(navController.graph.findStartDestination().id) {
                                                saveState = true
                                            }
                                            launchSingleTop = true
                                            restoreState = true
                                        }
                                    }
                                }
                            )
                        }
                    }
                }
            },
            containerColor = DarkBackground
        ) { innerPadding ->
            NavHost(
                navController = navController,
                startDestination = Screen.Home.route,
                modifier = Modifier.padding(innerPadding),
                enterTransition = { fadeIn(tween(240)) + slideInHorizontally(tween(240)) { it / 18 } },
                exitTransition = { fadeOut(tween(160)) },
                popEnterTransition = { fadeIn(tween(240)) },
                popExitTransition = { fadeOut(tween(160)) }
            ) {
                composable(Screen.Home.route) {
                    HomeScreen(
                        onExploreClick = { navController.navigate(Screen.Search.route) },
                        onLikedSongsClick = {
                            navController.navigate(Screen.LikedSongs.route)
                        },
                        onDownloadedSongsClick = {
                            navController.navigate(Screen.DownloadedSongs.route)
                        }
                    )
                }
                composable(Screen.Search.route) { SearchScreen() }
                composable(Screen.ForYou.route) { ForYouScreen(onExplore = { navController.navigate(Screen.Search.route) }, playerViewModel = playerViewModel) }
                composable(Screen.LikedSongs.route) {
                    LikedSongsScreen(
                        onBackClick = { navController.popBackStack() }
                    )
                }
                composable(Screen.DownloadedSongs.route) {
                    DownloadedSongsScreen(
                        onBackClick = { navController.popBackStack() }
                    )
                }
                composable(Screen.Profile.route) {
                    ProfileScreen(
                        tokenDataStore = tokenDataStore,
                        onLikedSongsClick = { navController.navigate(Screen.LikedSongs.route) },
                        onDownloadedSongsClick = { navController.navigate(Screen.DownloadedSongs.route) },
                        onExploreClick = { navController.navigate(Screen.Search.route) },
                        onLogout = onLogout
                    )
                }
            }
        }
        AnimatedVisibility(
            visible = showFullPlayer,
            enter = slideInVertically(tween(320)) { it } + fadeIn(tween(220)),
            exit = slideOutVertically(tween(280)) { it } + fadeOut(tween(200))
        ) {
            Surface(Modifier.fillMaxSize(), color = DarkBackground) {
                FullPlayerScreen(playerViewModel = playerViewModel, onDismiss = { showFullPlayer = false })
            }
        }
        BackHandler(enabled = showFullPlayer) { showFullPlayer = false }
    }
}

// ── Mini Player ───────────────────────────────────────────────────────────────
@Composable
fun MiniPlayer(
    title: String, albumArt: String?, artist: String?, isPlaying: Boolean, progress: Float,
    onTogglePlay: () -> Unit, onPrevious: () -> Unit, onNext: () -> Unit, onExpand: () -> Unit
) {
    Surface(modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 6.dp),
        shape = RoundedCornerShape(18.dp), color = DarkCardElevated, shadowElevation = 12.dp) {
        Column {
            Row(Modifier.fillMaxWidth().padding(6.dp), verticalAlignment = Alignment.CenterVertically) {
                Row(Modifier.weight(1f).clip(RoundedCornerShape(12.dp))
                    .clickable(onClickLabel = "Open player", onClick = onExpand).padding(4.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    AlbumArtwork(albumArt, Modifier.size(48.dp))
                    Spacer(Modifier.width(10.dp))
                    Column(Modifier.weight(1f)) {
                        Text(title, style = MaterialTheme.typography.titleSmall, color = TextPrimary,
                            maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(artist ?: "Now playing", style = MaterialTheme.typography.bodySmall,
                            color = TextSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
                PlaybackButton(Icons.Default.SkipPrevious, "Previous", onPrevious)
                PlaybackButton(if (isPlaying) Icons.Default.Pause else Icons.Default.PlayArrow,
                    if (isPlaying) "Pause" else "Play", onTogglePlay, prominent = true)
                PlaybackButton(Icons.Default.SkipNext, "Next", onNext)
            }
            LinearProgressIndicator(progress = { progress.coerceIn(0f, 1f) },
                modifier = Modifier.fillMaxWidth().height(3.dp), color = Accent, trackColor = DarkCard)
        }
    }
}

// ── Home Screen ───────────────────────────────────────────────────────────────
@Composable
fun HomeScreen(
    onLikedSongsClick: () -> Unit,
    onDownloadedSongsClick: () -> Unit,
    onExploreClick: () -> Unit,
    homeViewModel: HomeViewModel = viewModel()
) {
    val recentSongs by homeViewModel.recentSongs.collectAsStateWithLifecycle()
    val isLoading by homeViewModel.isLoading.collectAsStateWithLifecycle()
    val error by homeViewModel.error.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        homeViewModel.fetchRecentSongs()
    }

    LaunchedEffect(error) {
        error?.let {
            snackbarHostState.showSnackbar(it)
            homeViewModel.clearError()
        }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
        containerColor = DarkBackground
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        listOf(GradientTop, GradientMid, DarkBackground),
                        endY = 600f
                    )
                )
                .padding(padding)
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(24.dp)
        ) {
            item {
                Spacer(modifier = Modifier.height(24.dp))
                Text(
                    dynamicGreeting(),
                    fontSize = 32.sp,
                    fontWeight = FontWeight.ExtraBold,
                    color = TextPrimary
                )
            }

            item {
                Text(
                    "Your collection",
                    fontSize = 20.sp,
                    fontWeight = FontWeight.Bold,
                    color = TextPrimary
                )
                Spacer(modifier = Modifier.height(12.dp))
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Box(modifier = Modifier.weight(1f)) {
                            PlaylistItem(
                                name = "Liked Songs",
                                icon = Icons.Default.Favorite,
                                onClick = onLikedSongsClick
                            )
                        }
                        Box(modifier = Modifier.weight(1f)) {
                            PlaylistItem(
                                name = "Downloaded",
                                icon = Icons.Default.Download,
                                onClick = onDownloadedSongsClick
                            )
                        }
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Box(modifier = Modifier.weight(1f)) {
                            PlaylistItem(
                                name = "Explore music",
                                icon = Icons.Default.Search,
                                onClick = onExploreClick
                            )
                        }
                        Box(modifier = Modifier.weight(1f)) {}
                    }
                }
            }

            item {
                Text(
                    "Recently Played",
                    fontSize = 20.sp,
                    fontWeight = FontWeight.Bold,
                    color = TextPrimary
                )
                Spacer(modifier = Modifier.height(12.dp))

                when {
                    isLoading -> {
                        LazyRow(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                            items(4) { _ -> ShimmerSongCard() }
                        }
                    }
                    recentSongs.isEmpty() -> {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(120.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Icon(
                                    Icons.Default.MusicNote,
                                    contentDescription = null,
                                    tint = TextMuted,
                                    modifier = Modifier.size(40.dp)
                                )
                                Spacer(modifier = Modifier.height(8.dp))
                                Text(
                                    "Your listening history starts here.",
                                    fontSize = 14.sp,
                                    color = TextMuted,
                                    textAlign = androidx.compose.ui.text.style.TextAlign.Center
                                )
                                TextButton(onClick = onExploreClick) { Text("Explore music") }
                            }
                        }
                    }
                    else -> {
                        LazyRow(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                            items(recentSongs) { song ->
                                TrendingSongCard(
                                    title = song.title,
                                    artist = song.artistName ?: "Unknown Artist",
                                    imageUrl = song.thumbnailUrl ?: "",
                                    onClick = { homeViewModel.playSong(song) }
                                )
                            }
                        }
                    }
                }
            }
            item { Spacer(modifier = Modifier.height(16.dp)) }
        }
    }
}

// ── Search Screen ─────────────────────────────────────────────────────────────
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SearchScreen(searchViewModel: SearchViewModel = viewModel()) {
    val displayQuery by searchViewModel.query.collectAsStateWithLifecycle()
    val suggestions by searchViewModel.suggestions.collectAsStateWithLifecycle()
    val isLoading by searchViewModel.isLoading.collectAsStateWithLifecycle()
    val error by searchViewModel.error.collectAsStateWithLifecycle()
    val focusManager = LocalFocusManager.current
    val snackbarHostState = remember { SnackbarHostState() }
    var inputText by rememberSaveable { mutableStateOf("") }

    LaunchedEffect(error) {
        error?.let {
            snackbarHostState.showSnackbar(it)
            searchViewModel.clearError()
        }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
        containerColor = DarkBackground
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(DarkBackground)
                .padding(padding)
                .padding(horizontal = 16.dp)
        ) {
            Spacer(modifier = Modifier.height(16.dp))
            Text(
                "Search",
                fontSize = 28.sp,
                fontWeight = FontWeight.ExtraBold,
                color = TextPrimary
            )
            Spacer(modifier = Modifier.height(16.dp))

            TextField(
                value = inputText,
                onValueChange = {
                    inputText = it
                    searchViewModel.updateQuery(it)
                },
                placeholder = { Text("Find songs and artists", color = TextSecondary) },
                leadingIcon = {
                    Icon(Icons.Default.Search, contentDescription = null, tint = TextSecondary)
                },
                trailingIcon = {
                    if (inputText.isNotBlank()) {
                        IconButton(onClick = {
                            inputText = ""
                            searchViewModel.updateQuery("")
                            focusManager.clearFocus()
                        }) {
                            Icon(Icons.Default.Clear, contentDescription = "Clear", tint = TextSecondary)
                        }
                    }
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(10.dp)),
                colors = TextFieldDefaults.colors(
                    focusedContainerColor = DarkCard,
                    unfocusedContainerColor = DarkCard,
                    focusedTextColor = TextPrimary,
                    unfocusedTextColor = TextPrimary,
                    focusedIndicatorColor = Color.Transparent,
                    unfocusedIndicatorColor = Color.Transparent,
                    cursorColor = Accent
                ),
                singleLine = true
            )
            Spacer(modifier = Modifier.height(16.dp))

            when {
                isLoading -> {
                    LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        items(5) { _ -> ShimmerSongRow() }
                    }
                }
                inputText.isNotBlank() && suggestions.isEmpty() && !isLoading -> {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 48.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            "No results for \"$inputText\"",
                            color = TextMuted,
                            fontSize = 15.sp
                        )
                    }
                }
                inputText.isNotBlank() -> {
                    LazyColumn(
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                        modifier = Modifier.fillMaxSize()
                    ) {
                        items(suggestions) { song ->
                            SearchResultRow(
                                song = song,
                                onClick = {
                                    focusManager.clearFocus()
                                    searchViewModel.playSong(song)
                                }
                            )
                        }
                    }
                }
                else -> {
                    // Browse prompt when no query
                    Spacer(modifier = Modifier.height(24.dp))
                    Text(
                        "Start typing to search for your\nfavorite songs and artists",
                        color = TextMuted,
                        fontSize = 15.sp,
                        lineHeight = 22.sp
                    )
                }
            }
        }
    }
}

// ── Profile Screen ─────────────────────────────────────────────────────────────
@Composable
fun ProfileScreen(
    tokenDataStore: TokenDataStore,
    onLogout: () -> Unit,
    onLikedSongsClick: () -> Unit,
    onDownloadedSongsClick: () -> Unit,
    onExploreClick: () -> Unit
) {
    val username by tokenDataStore.usernameFlow.collectAsState(initial = "")
    val email by tokenDataStore.emailFlow.collectAsState(initial = "")
    val scope = rememberCoroutineScope()

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(listOf(GradientTop, DarkBackground), endY = 500f)
            )
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Spacer(modifier = Modifier.height(40.dp))

            // Avatar
            Box(
                modifier = Modifier
                    .size(110.dp)
                    .clip(CircleShape)
                    .background(Accent),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    (username?.firstOrNull()?.uppercaseChar() ?: '?').toString(),
                    fontSize = 48.sp,
                    fontWeight = FontWeight.ExtraBold,
                    color = Color.Black
                )
            }

            Spacer(modifier = Modifier.height(20.dp))

            Text(
                username ?: "User",
                fontSize = 26.sp,
                fontWeight = FontWeight.ExtraBold,
                color = TextPrimary
            )
            Text(
                email ?: "",
                fontSize = 14.sp,
                color = TextSecondary,
                modifier = Modifier.padding(top = 4.dp)
            )

            Spacer(modifier = Modifier.height(40.dp))
            HorizontalDivider(color = DarkCard)
            Spacer(modifier = Modifier.height(24.dp))

            // Library shortcuts
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                StatItem(Icons.Default.Search, "Explore", onExploreClick)
                StatItem(Icons.Default.Favorite, "Liked Songs", onLikedSongsClick)
                StatItem(Icons.Default.Download, "Downloads", onDownloadedSongsClick)
            }

            Spacer(modifier = Modifier.height(48.dp))

            // Logout button
            OutlinedButton(
                onClick = {
                    scope.launch {
                        tokenDataStore.clearAuthData()
                        onLogout()
                    }
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(52.dp),
                shape = RoundedCornerShape(26.dp),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = ErrorRed),
                border = androidx.compose.foundation.BorderStroke(1.dp, ErrorRed)
            ) {
                Icon(Icons.AutoMirrored.Filled.Logout, contentDescription = null, modifier = Modifier.size(20.dp))
                Spacer(modifier = Modifier.width(8.dp))
                Text("Log Out", fontWeight = FontWeight.Bold, fontSize = 15.sp)
            }

            Spacer(modifier = Modifier.height(24.dp))
        }
    }
}

// ── Sub-components ─────────────────────────────────────────────────────────────
@Composable
fun StatItem(icon: ImageVector, label: String, onClick: () -> Unit) {
    Column(Modifier.clip(RoundedCornerShape(16.dp)).clickable(onClick = onClick).padding(12.dp),
        horizontalAlignment = Alignment.CenterHorizontally) {
        Icon(icon, null, tint = Accent, modifier = Modifier.size(28.dp))
        Spacer(Modifier.height(8.dp))
        Text(label, style = MaterialTheme.typography.labelSmall, color = TextSecondary)
    }
}

@Composable
fun PlaylistItem(name: String, icon: ImageVector, onClick: () -> Unit) {
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(DarkCard)
        .clickable(onClick = onClick).padding(16.dp)) {
        Icon(icon, null, tint = Accent, modifier = Modifier.size(32.dp))
        Spacer(Modifier.height(20.dp))
        Text(name, color = TextPrimary, style = MaterialTheme.typography.titleSmall)
    }
}

@Composable
fun TrendingSongCard(title: String, artist: String, imageUrl: String, onClick: () -> Unit) {
    Column(
        modifier = Modifier
            .width(176.dp).clip(RoundedCornerShape(16.dp))
            .clickable { onClick() }
    ) {
        AlbumArtwork(imageUrl, Modifier.size(176.dp))
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            title,
            color = TextPrimary,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            fontSize = 14.sp
        )
        Text(
            artist,
            color = TextSecondary,
            fontSize = 12.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis
        )
    }
}

@Composable
fun SearchResultRow(song: SongResponse, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .clickable { onClick() }
            .padding(vertical = 8.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        AlbumArtwork(song.thumbnailUrl, Modifier.size(64.dp))
        Spacer(modifier = Modifier.width(14.dp))
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
        Icon(
            Icons.Default.PlayArrow,
            contentDescription = null,
            tint = TextMuted,
            modifier = Modifier.size(20.dp)
        )
    }
}

private fun dynamicGreeting(): String {
    return when (Calendar.getInstance().get(Calendar.HOUR_OF_DAY)) {
        in 5..11 -> "Good morning"
        in 12..17 -> "Good afternoon"
        in 18..21 -> "Good evening"
        else -> "Late night listening"
    }
}