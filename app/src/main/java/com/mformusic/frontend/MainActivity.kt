package com.mformusic.frontend

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.mformusic.frontend.data.TokenDataStore
import com.mformusic.frontend.navigation.Screen
import com.mformusic.frontend.network.PlayerManager
import com.mformusic.frontend.network.RetrofitClient
import com.mformusic.frontend.ui.screens.LoginScreen
import com.mformusic.frontend.ui.screens.MainAppScreen
import com.mformusic.frontend.ui.screens.RegisterScreen
import com.mformusic.frontend.ui.screens.SplashScreen
import com.mformusic.frontend.ui.theme.MforMusicTheme
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController

class MainActivity : ComponentActivity() {

    private lateinit var tokenDataStore: TokenDataStore

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Initialize singletons
        tokenDataStore = TokenDataStore(applicationContext)
        RetrofitClient.init(tokenDataStore)
        PlayerManager.initialize(this)

        setContent {
            MforMusicTheme {
                val navController = rememberNavController()

                NavHost(
                    navController = navController,
                    startDestination = Screen.Splash.route
                ) {
                    composable(Screen.Splash.route) {
                        SplashScreen(navController, tokenDataStore)
                    }
                    composable(Screen.Login.route) {
                        LoginScreen(navController, tokenDataStore)
                    }
                    composable(Screen.Register.route) {
                        RegisterScreen(navController, tokenDataStore)
                    }
                    composable(Screen.Home.route) {
                        // Home is the root of the main app scaffold
                        MainAppScreen(tokenDataStore)
                    }
                }
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        // Prevent ExoPlayer memory leak
        PlayerManager.release()
    }
}