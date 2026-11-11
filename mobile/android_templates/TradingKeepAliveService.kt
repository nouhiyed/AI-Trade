package com.example.ai_trade

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.os.SystemClock
import java.net.HttpURLConnection
import java.net.URL

class TradingKeepAliveService : Service() {
    @Volatile private var running = false
    private var worker: Thread? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private val channelId = "ai_trade_background"
    @Volatile private var lastLaunchAttemptMs = 0L

    override fun onCreate() {
        super.onCreate()
        createChannel()
        val pm = getSystemService(POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "AITrade:BackgroundMonitor")
        wakeLock?.setReferenceCounted(false)
        try { wakeLock?.acquire() } catch (_: Exception) {}
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "com.example.ai_trade.RETRY_BACKEND") {
            lastLaunchAttemptMs = 0L
        }
        val notification = buildNotification("Starting AI-Trader background engine")
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(1001, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(1001, notification)
        }
        if (!running) startBackendMonitor()
        return START_STICKY
    }

    private fun startBackendMonitor() {
        running = true
        worker = Thread {
            while (running) {
                val message = if (checkBackend()) {
                    lastLaunchAttemptMs = 0L
                    "Trading engine active • Termux connected"
                } else {
                    requestTermuxBackend()
                }
                (getSystemService(NOTIFICATION_SERVICE) as NotificationManager)
                    .notify(1001, buildNotification(message))
                try { Thread.sleep(15000) } catch (_: InterruptedException) { break }
            }
        }.apply { name = "AITrade-Backend-Watch"; isDaemon = true; start() }
    }

    private fun requestTermuxBackend(): String {
        val now = SystemClock.elapsedRealtime()
        if (now - lastLaunchAttemptMs < 30000L) {
            return "Waiting for Termux trading engine to start"
        }
        lastLaunchAttemptMs = now

        try {
            packageManager.getPackageInfo("com.termux", 0)
        } catch (_: Exception) {
            return "Termux is not installed • Install Termux to run the engine"
        }

        if (Build.VERSION.SDK_INT >= 23 &&
            checkSelfPermission("com.termux.permission.RUN_COMMAND") != PackageManager.PERMISSION_GRANTED
        ) {
            return "Termux permission needed • Allow RUN_COMMAND in app permissions"
        }

        val script = """
            cd /data/data/com.termux/files/home/AI-Trader-clean || exit 7
            if ! python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2)' >/dev/null 2>&1; then
              if [ ! -f api/main.py ]; then
                echo "AI-Trader repository not found in ~/AI-Trader" >&2
                exit 7
              fi
              mkdir -p logs
              nohup env PYTHONPATH=. python -u api/main.py >> logs/api-background.log 2>&1 </dev/null &
            fi
        """.trimIndent()

        return try {
            val command = Intent("com.termux.RUN_COMMAND").apply {
                setClassName("com.termux", "com.termux.app.RunCommandService")
                putExtra("com.termux.RUN_COMMAND_PATH", "/data/data/com.termux/files/usr/bin/bash")
                putExtra("com.termux.RUN_COMMAND_ARGUMENTS", arrayOf("-lc", script))
                putExtra("com.termux.RUN_COMMAND_WORKDIR", "/data/data/com.termux/files/home/AI-Trader-clean")
                putExtra("com.termux.RUN_COMMAND_BACKGROUND", true)
                putExtra("com.termux.RUN_COMMAND_LABEL", "AI-Trader background engine")
                putExtra("com.termux.RUN_COMMAND_DESCRIPTION", "Starts the local AI-Trader API and DEMO monitoring engine")
            }
            startService(command)
            "Starting trading engine in Termux • Waiting for API"
        } catch (_: SecurityException) {
            "Termux access denied • Enable allow-external-apps and RUN_COMMAND permission"
        } catch (_: Exception) {
            "Could not start Termux • Open Termux once and check permissions"
        }
    }

    private fun checkBackend(): Boolean {
        var connection: HttpURLConnection? = null
        return try {
            connection = URL("http://127.0.0.1:8000/health").openConnection() as HttpURLConnection
            connection.requestMethod = "GET"
            connection.connectTimeout = 2500
            connection.readTimeout = 2500
            connection.responseCode in 200..299
        } catch (_: Exception) {
            false
        } finally {
            connection?.disconnect()
        }
    }

    private fun buildNotification(message: String): Notification {
        val launch = packageManager.getLaunchIntentForPackage(packageName)
        val pending = launch?.let {
            PendingIntent.getActivity(this, 0, it, PendingIntent.FLAG_UPDATE_CURRENT or
                (if (Build.VERSION.SDK_INT >= 23) PendingIntent.FLAG_IMMUTABLE else 0))
        }
        val builder = if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, channelId)
            else Notification.Builder(this)
        builder.setSmallIcon(android.R.drawable.ic_popup_sync)
            .setContentTitle("AI-Trader")
            .setContentText(message)
            .setStyle(Notification.BigTextStyle().bigText(message))
            .setOngoing(true)
            .setOnlyAlertOnce(true)
        if (pending != null) builder.setContentIntent(pending)
        return builder.build()
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
            manager.createNotificationChannel(NotificationChannel(
                channelId, "AI-Trader background service", NotificationManager.IMPORTANCE_LOW
            ).apply { description = "Shows whether the local trading engine is running" })
        }
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        running = false
        worker?.interrupt()
        try { if (wakeLock?.isHeld == true) wakeLock?.release() } catch (_: Exception) {}
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
