import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.ConnectException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;

/** Credential-free, bounded TCP probe. It never sends application requests. */
public final class NetworkProbe {
    private static InetAddress address(String value) throws Exception {
        String[] parts = value.split("\\.", -1);
        if (parts.length != 4) throw new IllegalArgumentException();
        byte[] bytes = new byte[4];
        for (int i = 0; i < 4; i++) {
            if (!parts[i].matches("0|[1-9][0-9]{0,2}")) throw new IllegalArgumentException();
            int n = Integer.parseInt(parts[i]);
            if (n > 255) throw new IllegalArgumentException();
            bytes[i] = (byte) n;
        }
        return InetAddress.getByAddress(bytes); // Never turn a DNS error into a denied connection.
    }

    private static void serve(String nonce) throws Exception {
        if (!nonce.matches("[a-f0-9]{32}")) throw new IllegalArgumentException();
        for (int port : new int[] {19067, 5432, 11434}) {
            ServerSocket server = new ServerSocket();
            server.bind(new InetSocketAddress("0.0.0.0", port), 32);
            Thread thread = new Thread(() -> {
                while (!server.isClosed()) {
                    try (Socket client = server.accept()) {
                        client.setSoTimeout(1000);
                        client.getOutputStream().write((nonce + "\n").getBytes(StandardCharsets.US_ASCII));
                    } catch (Exception ignored) {
                        // A client disconnect is normal. No request data is logged or retained.
                    }
                }
            });
            thread.setDaemon(true);
            thread.start();
        }
        System.out.println("PROBE_LISTENERS_READY");
        new CountDownLatch(1).await();
    }

    private static void connect(String line) throws Exception {
        String[] fields = line.split(" ", -1);
        if (fields.length != 5 || !fields[0].matches("[a-z0-9-]{1,80}")
                || !fields[4].matches("-|[a-f0-9]{32}")) throw new IllegalArgumentException();
        InetAddress ip = address(fields[1]);
        int port = Integer.parseInt(fields[2]);
        int timeout = Integer.parseInt(fields[3]);
        if (port < 1 || port > 65535 || timeout < 100 || timeout > 5000) throw new IllegalArgumentException();
        long start = System.nanoTime();
        String outcome;
        boolean established = false;
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(ip, port), timeout);
            established = true;
            socket.setSoTimeout(timeout);
            outcome = "connected";
            if (!fields[4].equals("-")) {
                byte[] expected = (fields[4] + "\n").getBytes(StandardCharsets.US_ASCII);
                byte[] actual = socket.getInputStream().readNBytes(expected.length);
                outcome = java.util.Arrays.equals(actual, expected) ? "nonce-matched" : "nonce-mismatch";
            }
        } catch (SocketTimeoutException exc) {
            outcome = established ? "read-timeout" : "connect-timeout";
        } catch (ConnectException exc) {
            outcome = "connection-refused";
        } catch (Exception exc) {
            outcome = "transport-error";
        }
        long elapsed = (System.nanoTime() - start) / 1000000;
        System.out.println("{\"id\":\"" + fields[0] + "\",\"outcome\":\"" + outcome
                + "\",\"elapsed_ms\":" + elapsed + "}");
    }

    public static void main(String[] args) {
        try {
            if (args.length == 2 && args[0].equals("serve")) {
                serve(args[1]);
            } else if (args.length == 1 && args[0].equals("connect")) {
                BufferedReader reader = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.US_ASCII));
                String line;
                int count = 0;
                while ((line = reader.readLine()) != null) {
                    if (++count > 32 || line.length() > 256) throw new IllegalArgumentException();
                    connect(line);
                }
            } else {
                throw new IllegalArgumentException();
            }
        } catch (Exception exc) {
            System.err.println("NETWORK_PROBE_INPUT_OR_STARTUP_ERROR");
            System.exit(2);
        }
    }
}
