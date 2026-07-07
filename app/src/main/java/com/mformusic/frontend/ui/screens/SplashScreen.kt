package com.mformusic.frontend.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.compose.material3.Text
import androidx.navigation.NavController
import com.mformusic.frontend.data.TokenDataStore
import com.mformusic.frontend.navigation.Screen
import com.mformusic.frontend.ui.theme.DarkBackground
import com.mformusic.frontend.ui.theme.GradientTop
import com.mformusic.frontend.ui.theme.SpotifyGreen
import kotlinx.coroutines.delay

@Composable
fun SplashScreen(navController: NavController, tokenDataStore: TokenDataStore) {
    // Check auth token and navigate
    LaunchedEffect(Unit) {
        delay(1000L) // Brief splash display
        val hasToken = tokenDataStore.hasToken()
        val destination = if (hasToken) Screen.Home.route else Screen.Login.route
        navController.navigate(destination) {
            popUpTo(Screen.Splash.route) { inclusive = true }
        }
    }

    // Splash UI
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(listOf(GradientTop, DarkBackground))
            ),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                "M",
                fontSize = 80.sp,
                fontWeight = FontWeight.ExtraBold,
                color = SpotifyGreen
            )
            Text(
                "for Music",
                fontSize = 22.sp,
                fontWeight = FontWeight.Medium,
                color = Color.White
            )
        }
    }
}
