import android.content.ClipData;
import android.os.IBinder;
import java.lang.reflect.Method;

/**
 * UAT: 기기 클립보드에 텍스트(Base64 UTF-8)를 넣는다 — shell 권한, app_process 로 실행.
 * adb `input text` 는 ASCII 만 넣을 수 있어서 한글 등은 이 클립보드 + 붙여넣기로 입력한다.
 *
 * 빌드(한 번): references/drivers.md §1.4
 *   javac --release 8 -cp <sdk>/platforms/android-<N>/android.jar ClipSet.java
 *   <sdk>/build-tools/<ver>/d8 --output . ClipSet.class      → classes.dex
 *   adb push classes.dex /data/local/tmp/uat-clip.dex
 * 실행: adb shell CLASSPATH=/data/local/tmp/uat-clip.dex app_process /system/bin ClipSet <base64>
 */
public class ClipSet {
    public static void main(String[] args) throws Exception {
        String text = new String(android.util.Base64.decode(args[0], 0), "UTF-8");
        IBinder b = (IBinder) Class.forName("android.os.ServiceManager")
                .getMethod("getService", String.class).invoke(null, "clipboard");
        Object clip = Class.forName("android.content.IClipboard$Stub")
                .getMethod("asInterface", IBinder.class).invoke(null, b);
        ClipData data = ClipData.newPlainText("uat", text);
        for (Method m : clip.getClass().getMethods()) {
            if (!m.getName().equals("setPrimaryClip")) continue;
            Class<?>[] p = m.getParameterTypes();
            Object[] a = new Object[p.length];
            a[0] = data;
            boolean firstString = true;
            for (int i = 1; i < p.length; i++) {
                if (p[i] == String.class) { a[i] = firstString ? "com.android.shell" : null; firstString = false; }
                else if (p[i] == int.class) a[i] = 0;
            }
            m.invoke(clip, a);
            System.out.println("ok");
            return;
        }
        System.out.println("setPrimaryClip not found");
    }
}
