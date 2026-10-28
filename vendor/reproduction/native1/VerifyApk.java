import com.android.apksig.ApkVerifier;
import java.io.File;

/** Cryptographically verify the staged APK using the build's apksig library. */
class VerifyApk {
    public static void main(String[] args) throws Exception {
        ApkVerifier.Result result = new ApkVerifier.Builder(new File(args[0])).build().verify();
        for (Object error : result.getErrors()) {
            System.err.println(error);
        }
        if (!result.isVerified()) {
            throw new IllegalStateException("APK signature verification failed");
        }
        System.out.println("APK_SIGNATURE_VERIFIED");
    }
}
