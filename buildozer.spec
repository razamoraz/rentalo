[app]

# (str) Title of your application
title = renTalo

# (str) Package name
package.name = rentalo

# (str) Package domain (needed for android/ios packaging)
package.domain = org.rentalo

# (str) Source code where the main.py lives
source.dir = .

# (list) Source files to include
source.include_exts = py,png,jpg,kv,atlas,json,db

# (list) Source files to exclude
source.exclude_dirs = tests,bin,.venv,.pytest_cache,.git,exportaciones_rentalo,exportaciones_rentafacil

# (str) Application versioning
version = 1.0.0

# (list) Application requirements
requirements = python3,kivy==2.3.2,kivymd==1.2.0,pillow,plyer==2.1.0

# (str) Supported orientation (one of landscape, sensorLandscape, portrait or all)
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (list) Permissions for WhatsApp links, storage backup, local notifications
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,POST_NOTIFICATIONS,VIBRATE,WAKE_LOCK,RECEIVE_BOOT_COMPLETED

# (int) Target Android API
android.api = 34

# (int) Minimum API your APK will support
android.minapi = 21

# (int) Android SDK version to use
android.sdk = 34

# (str) Android NDK version to use
android.ndk = 25b

# (bool) Automatically accept SDK license
android.accept_sdk_license = True

# (str) The Android archs to build for
android.archs = arm64-v8a

# (bool) Enables Android auto backup feature
android.allow_backup = True

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug)
log_level = 2

# (int) Display warning if buildozer is run as root
warn_on_root = 1
