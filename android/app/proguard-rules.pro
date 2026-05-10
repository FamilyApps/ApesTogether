# Keep kotlinx.serialization classes (uses reflection at runtime for @Serializable lookups).
-keep class kotlinx.serialization.** { *; }
-keepclasseswithmembers class * {
    @kotlinx.serialization.Serializable <fields>;
}
-keepclasseswithmembers class * {
    @kotlinx.serialization.Serializable <methods>;
}

# Keep Retrofit annotations.
-keepattributes Signature, InnerClasses, EnclosingMethod, *Annotation*
-keep class retrofit2.** { *; }

# Keep all data classes in our models package (they are decoded by kotlinx.serialization).
-keep class ai.apestogether.data.models.** { *; }

# Hilt / Dagger
-keep class dagger.hilt.** { *; }
-keep class * extends dagger.hilt.android.HiltAndroidApp
