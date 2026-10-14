import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.AccessDeniedException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.OpenOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Java 21 translation of the supplied CBTRN02C.
 *
 * Invocation:
 *   PosttranCandidate INPUT_DIRECTORY OUTPUT_DIRECTORY CURRENT_DATE
 *
 * Input logical files are resolved as DD, DD.txt, then DD.bin.
 * Inputs may be ASCII transport records or fixed-block IBM037 before images.
 * The packet's "PUBLIC FIXED BYTES HEX" representation is also accepted.
 *
 * Each output image is published as DD, DD.txt and DD.bin. All three names
 * contain the same newline-separated, fixed-width ASCII transport records.
 * RETURN-CODE and return-code.txt contain the decimal completion code.
 * The same code is passed to System.exit; the files retain the full value
 * when an operating system limits process exit statuses to eight bits.
 *
 * Output files must not already exist. CREATE_NEW prevents an output alias,
 * symbolic link, or existing hard link from overwriting a supplied image.
 *
 * Amounts are represented internally as integral cents. No floating-point
 * operations, host clock, network, subprocesses, or external libraries are
 * used.
 */
public final class PosttranCandidate {
    private static final int ABEND_CODE = 999;
    private static final long COUNTER_MODULUS = 1_000_000_000L;
    private static final Charset IBM037 = Charset.forName("IBM037");

    private static final int[] EBCDIC_ORDER = makeEbcdicOrder();

    private static final Comparator<String> KEY_ORDER = (left, right) -> {
        int length = Math.min(left.length(), right.length());
        for (int i = 0; i < length; i++) {
            int difference =
                    EBCDIC_ORDER[left.charAt(i)] - EBCDIC_ORDER[right.charAt(i)];
            if (difference != 0) {
                return difference;
            }
        }
        return Integer.compare(left.length(), right.length());
    };

    private PosttranCandidate() {
    }

    public static void main(String[] args) {
        if (args.length != 3) {
            System.err.println(
                    "Usage: PosttranCandidate INPUT_DIRECTORY "
                    + "OUTPUT_DIRECTORY CURRENT_DATE");
            System.exit(64);
            return;
        }

        int code = run(Path.of(args[0]), Path.of(args[1]), args[2]);
        System.exit(code);
    }

    public static int run(Path inputDirectory,
                          Path outputDirectory,
                          String currentDate) {
        Path input = inputDirectory.toAbsolutePath().normalize();
        Path output = outputDirectory.toAbsolutePath().normalize();

        if (output.equals(input) || output.startsWith(input)) {
            System.err.println(
                    "OUTPUT_DIRECTORY must be outside INPUT_DIRECTORY.");
            return ABEND_CODE;
        }

        final String timestamp;
        try {
            timestamp = scenarioTimestamp(currentDate);
        } catch (IllegalArgumentException ex) {
            System.err.println("Invalid CURRENT_DATE: " + ex.getMessage());
            return ABEND_CODE;
        }

        try {
            Files.createDirectories(output);
        } catch (IOException | SecurityException ex) {
            System.err.println("Cannot create OUTPUT_DIRECTORY.");
            return ABEND_CODE;
        }

        Program program = new Program(input, output, timestamp);
        int code = program.execute();

        try {
            byte[] completion = (Integer.toString(code) + "\n")
                    .getBytes(StandardCharsets.US_ASCII);
            writeNew(output.resolve("RETURN-CODE"), completion);
            writeNew(output.resolve("return-code.txt"), completion);
        } catch (IOException | SecurityException ex) {
            System.err.println("Cannot publish the completion code.");
            return ABEND_CODE;
        }

        return code;
    }

    /*
     * Copybook layouts. Offsets are zero-based; lengths exclude transport LF.
     */
    private record Field(int offset, int length) {
    }

    private static final class Account {
        static final int LENGTH = 300;
        static final Field ID = new Field(0, 11);
        static final Field ACTIVE_STATUS = new Field(11, 1);
        static final Field CURRENT_BALANCE = new Field(12, 12);
        static final Field CREDIT_LIMIT = new Field(24, 12);
        static final Field CASH_CREDIT_LIMIT = new Field(36, 12);
        static final Field OPEN_DATE = new Field(48, 10);
        static final Field EXPIRATION_DATE = new Field(58, 10);
        static final Field REISSUE_DATE = new Field(68, 10);
        static final Field CYCLE_CREDIT = new Field(78, 12);
        static final Field CYCLE_DEBIT = new Field(90, 12);
        static final Field ADDRESS_ZIP = new Field(102, 10);
        static final Field GROUP_ID = new Field(112, 10);
        static final Field FILLER = new Field(122, 178);
    }

    private static final class Xref {
        static final int LENGTH = 50;
        static final Field CARD_NUMBER = new Field(0, 16);
        static final Field CUSTOMER_ID = new Field(16, 9);
        static final Field ACCOUNT_ID = new Field(25, 11);
        static final Field FILLER = new Field(36, 14);
    }

    private static final class Category {
        static final int LENGTH = 50;
        static final int KEY_LENGTH = 17;
        static final Field ACCOUNT_ID = new Field(0, 11);
        static final Field TYPE_CODE = new Field(11, 2);
        static final Field CATEGORY_CODE = new Field(13, 4);
        static final Field BALANCE = new Field(17, 11);
        static final Field FILLER = new Field(28, 22);
    }

    /* CVTRA05Y and CVTRA06Y have identical layouts. */
    private static final class Transaction {
        static final int LENGTH = 350;
        static final Field ID = new Field(0, 16);
        static final Field TYPE_CODE = new Field(16, 2);
        static final Field CATEGORY_CODE = new Field(18, 4);
        static final Field SOURCE = new Field(22, 10);
        static final Field DESCRIPTION = new Field(32, 100);
        static final Field AMOUNT = new Field(132, 11);
        static final Field MERCHANT_ID = new Field(143, 9);
        static final Field MERCHANT_NAME = new Field(152, 50);
        static final Field MERCHANT_CITY = new Field(202, 50);
        static final Field MERCHANT_ZIP = new Field(252, 10);
        static final Field CARD_NUMBER = new Field(262, 16);
        static final Field ORIGINAL_TIMESTAMP = new Field(278, 26);
        static final Field PROCESS_TIMESTAMP = new Field(304, 26);
        static final Field FILLER = new Field(330, 20);

        static final Field[] POST_MOVES = {
                ID, TYPE_CODE, CATEGORY_CODE, SOURCE, DESCRIPTION, AMOUNT,
                MERCHANT_ID, MERCHANT_NAME, MERCHANT_CITY, MERCHANT_ZIP,
                CARD_NUMBER, ORIGINAL_TIMESTAMP
        };
    }

    private static final class Reject {
        static final int LENGTH = 430;
        static final Field TRANSACTION_DATA = new Field(0, 350);
        static final Field REASON = new Field(350, 4);
        static final Field DESCRIPTION = new Field(354, 76);
    }

    private static final class Program {
        private final Path input;
        private final Path output;
        private final String timestamp;

        private DailyFile dailyFile;
        private IndexedFile transactionFile;
        private IndexedFile xrefFile;
        private Sink rejectFile;
        private IndexedFile accountFile;
        private IndexedFile categoryFile;

        private char[] dailyRecord;
        private char[] xrefRecord = initialXref();
        private char[] accountRecord = initialAccount();
        private final char[] transactionRecord = initialTransaction();
        private char[] categoryRecord = initialCategory();

        private int validationReason;
        private String validationDescription = "";
        private long transactionCount;
        private long rejectCount;

        Program(Path input, Path output, String timestamp) {
            this.input = input;
            this.output = output;
            this.timestamp = timestamp;
        }

        int execute() {
            System.out.println("START OF EXECUTION OF PROGRAM CBTRN02C");

            try {
                openFiles();

                while (true) {
                    dailyRecord = dailyFile.read();
                    if ("10".equals(dailyFile.status)) {
                        break;
                    }
                    require("ERROR READING DALYTRAN FILE", dailyFile.status);

                    transactionCount =
                            (transactionCount + 1) % COUNTER_MODULUS;
                    validationReason = 0;
                    validationDescription = "";

                    validateTransaction();

                    if (validationReason == 0) {
                        postTransaction();
                    } else {
                        rejectCount = (rejectCount + 1) % COUNTER_MODULUS;
                        writeReject();
                    }
                }

                closeFiles();

                System.out.println("TRANSACTIONS PROCESSED :"
                        + unsigned(transactionCount, 9));
                System.out.println("TRANSACTIONS REJECTED  :"
                        + unsigned(rejectCount, 9));
                int returnCode = rejectCount > 0 ? 4 : 0;
                System.out.println("END OF EXECUTION OF PROGRAM CBTRN02C");
                return returnCode;
            } catch (Abend ex) {
                return ABEND_CODE;
            } catch (DecimalDataException ex) {
                System.err.println(ex.getMessage());
                System.out.println("ABENDING PROGRAM");
                return ABEND_CODE;
            } finally {
                /*
                 * No rollback: successful earlier writes remain visible,
                 * including balance changes preceding a duplicate TRAN-ID.
                 */
                quietlyClose(transactionFile);
                quietlyClose(xrefFile);
                quietlyClose(accountFile);
                quietlyClose(categoryFile);
                if (rejectFile != null && rejectFile.open) {
                    rejectFile.close();
                }
                if (dailyFile != null && dailyFile.open) {
                    dailyFile.close();
                }
            }
        }

        private void openFiles() {
            try {
                dailyFile = DailyFile.open(input);
            } catch (FileStatusException ex) {
                abort("ERROR OPENING DALYTRAN", ex.status);
            }

            try {
                /*
                 * The source says OPEN OUTPUT, not I-O. Consume the supplied
                 * before image, when present, but do not retain its records
                 * or use its keys for duplicate detection.
                 */
                readOptionalImage(input, "TRANFILE");
                transactionFile = IndexedFile.openOutput(
                        output, "TRANFILE", Transaction.LENGTH, 16);
            } catch (FileStatusException ex) {
                abort("ERROR OPENING TRANSACTION FILE", ex.status);
            }

            try {
                xrefFile = IndexedFile.openExisting(
                        input, output, "XREFFILE", Xref.LENGTH, 16, false);
            } catch (FileStatusException ex) {
                abort("ERROR OPENING CROSS REF FILE", ex.status);
            }

            try {
                rejectFile = Sink.open(output, "DALYREJS", Reject.LENGTH);
            } catch (FileStatusException ex) {
                abort("ERROR OPENING DALY REJECTS FILE", ex.status);
            }

            try {
                accountFile = IndexedFile.openExisting(
                        input, output, "ACCTFILE", Account.LENGTH, 11, true);
            } catch (FileStatusException ex) {
                abort("ERROR OPENING ACCOUNT MASTER FILE", ex.status);
            }

            try {
                categoryFile = IndexedFile.openExisting(
                        input, output, "TCATBALF",
                        Category.LENGTH, Category.KEY_LENGTH, true);
            } catch (FileStatusException ex) {
                abort("ERROR OPENING TRANSACTION BALANCE FILE", ex.status);
            }
        }

        private void validateTransaction() {
            // 1500-A-LOOKUP-XREF
            char[] found = xrefFile.read(
                    text(dailyRecord, Transaction.CARD_NUMBER));
            if (invalidKey(xrefFile.status)) {
                validationReason = 100;
                validationDescription = "INVALID CARD NUMBER FOUND";
            } else if (found != null) {
                xrefRecord = found;
            }

            if (validationReason != 0) {
                return;
            }

            // 1500-B-LOOKUP-ACCT
            found = accountFile.read(text(xrefRecord, Xref.ACCOUNT_ID));
            if (invalidKey(accountFile.status)) {
                validationReason = 101;
                validationDescription = "ACCOUNT RECORD NOT FOUND";
                return;
            }
            if (found != null) {
                accountRecord = found;
            }

            /*
             * WS-TEMP-BAL is S9(09)V99, one integer digit narrower than
             * the account amounts. There is no ON SIZE ERROR or ROUNDED.
             */
            long temporaryBalance = truncate(
                    zoned(accountRecord, Account.CYCLE_CREDIT)
                    - zoned(accountRecord, Account.CYCLE_DEBIT)
                    + zoned(dailyRecord, Transaction.AMOUNT),
                    11);

            if (zoned(accountRecord, Account.CREDIT_LIMIT)
                    < temporaryBalance) {
                validationReason = 102;
                validationDescription = "OVERLIMIT TRANSACTION";
            }

            /*
             * This is a separate IF. Expiration overrides reason 102.
             * The source compares the transaction's original date, not
             * CURRENT_DATE, and does not check active status.
             */
            String originalDate = new String(
                    dailyRecord, Transaction.ORIGINAL_TIMESTAMP.offset(), 10);
            if (KEY_ORDER.compare(
                    text(accountRecord, Account.EXPIRATION_DATE),
                    originalDate) < 0) {
                validationReason = 103;
                validationDescription =
                        "TRANSACTION RECEIVED AFTER ACCT EXPIRATION";
            }
        }

        private void postTransaction() {
            // 2000-POST-TRANSACTION: elementary moves, excluding FILLER.
            for (Field field : Transaction.POST_MOVES) {
                move(dailyRecord, field, transactionRecord, field);
            }
            putText(transactionRecord, Transaction.PROCESS_TIMESTAMP, timestamp);

            updateCategory();
            updateAccount();

            // 2900-WRITE-TRANSACTION-FILE
            transactionFile.write(transactionRecord);
            require("ERROR WRITING TO TRANSACTION FILE",
                    transactionFile.status);
        }

        private void writeReject() {
            // 2500-WRITE-REJECT-REC
            char[] record = spaces(Reject.LENGTH);
            System.arraycopy(dailyRecord, 0, record, 0, Transaction.LENGTH);
            putText(record, Reject.REASON, unsigned(validationReason, 4));
            putText(record, Reject.DESCRIPTION, validationDescription);

            rejectFile.append(record);
            require("ERROR WRITING TO REJECTS FILE", rejectFile.status);
        }

        private void updateCategory() {
            // 2700-UPDATE-TCATBAL
            String key = text(xrefRecord, Xref.ACCOUNT_ID)
                    + text(dailyRecord, Transaction.TYPE_CODE)
                    + text(dailyRecord, Transaction.CATEGORY_CODE);

            boolean create = false;
            char[] found = categoryFile.read(key);
            if (invalidKey(categoryFile.status)) {
                System.out.println("TCATBAL record not found for key : "
                        + key + ".. Creating.");
                create = true;
            } else if (found != null) {
                categoryRecord = found;
            }

            if (!"00".equals(categoryFile.status)
                    && !"23".equals(categoryFile.status)) {
                abort("ERROR READING TRANSACTION BALANCE FILE",
                        categoryFile.status);
            }

            long amount = zoned(dailyRecord, Transaction.AMOUNT);

            if (create) {
                // 2700-A-CREATE-TCATBAL-REC
                /*
                 * INITIALIZE without WITH FILLER leaves FILLER alone.
                 * Therefore a new category can inherit filler from the
                 * preceding successful READ into this working-storage item.
                 */
                initializeCategoryNamedFields(categoryRecord);
                move(xrefRecord, Xref.ACCOUNT_ID,
                        categoryRecord, Category.ACCOUNT_ID);
                move(dailyRecord, Transaction.TYPE_CODE,
                        categoryRecord, Category.TYPE_CODE);
                move(dailyRecord, Transaction.CATEGORY_CODE,
                        categoryRecord, Category.CATEGORY_CODE);
                putZoned(categoryRecord, Category.BALANCE, amount);

                categoryFile.write(categoryRecord);
                require("ERROR WRITING TRANSACTION BALANCE FILE",
                        categoryFile.status);
            } else {
                // 2700-B-UPDATE-TCATBAL-REC
                putZoned(categoryRecord, Category.BALANCE,
                        zoned(categoryRecord, Category.BALANCE) + amount);
                categoryFile.rewrite(categoryRecord);
                require("ERROR REWRITING TRANSACTION BALANCE FILE",
                        categoryFile.status);
            }
        }

        private void updateAccount() {
            // 2800-UPDATE-ACCOUNT-REC
            long amount = zoned(dailyRecord, Transaction.AMOUNT);

            putZoned(accountRecord, Account.CURRENT_BALANCE,
                    zoned(accountRecord, Account.CURRENT_BALANCE) + amount);

            if (amount >= 0) {
                putZoned(accountRecord, Account.CYCLE_CREDIT,
                        zoned(accountRecord, Account.CYCLE_CREDIT) + amount);
            } else {
                /*
                 * Deliberately ADD the negative amount to CYCLE_DEBIT;
                 * do not change this into adding its absolute value.
                 */
                putZoned(accountRecord, Account.CYCLE_DEBIT,
                        zoned(accountRecord, Account.CYCLE_DEBIT) + amount);
            }

            accountFile.rewrite(accountRecord);
            if (invalidKey(accountFile.status)) {
                validationReason = 109;
                validationDescription = "ACCOUNT RECORD NOT FOUND";
            }
            /*
             * The source does not check other rewrite statuses here and
             * does not reroute a post-time reason 109 to the reject writer.
             */
        }

        private void closeFiles() {
            require("ERROR CLOSING DALYTRAN FILE", dailyFile.close());
            require("ERROR CLOSING TRANSACTION FILE", transactionFile.close());
            require("ERROR CLOSING CROSS REF FILE", xrefFile.close());

            String rejectCloseStatus = rejectFile.close();
            if (!"00".equals(rejectCloseStatus)) {
                /*
                 * Preserve the source's unusual diagnostic: it moves
                 * XREFFILE-STATUS, not DALYREJS-STATUS, to IO-STATUS.
                 */
                abort("ERROR CLOSING DAILY REJECTS FILE", xrefFile.status);
            }

            require("ERROR CLOSING ACCOUNT FILE", accountFile.close());
            require("ERROR CLOSING TRANSACTION BALANCE FILE",
                    categoryFile.close());
        }

        private static void quietlyClose(IndexedFile file) {
            if (file != null && file.open) {
                file.close();
            }
        }
    }

    private static final class DailyFile {
        private final List<char[]> records;
        private int next;
        private boolean eof;
        private boolean open = true;
        private String status = "00";

        private DailyFile(List<char[]> records) {
            this.records = records;
        }

        static DailyFile open(Path directory) throws FileStatusException {
            byte[] bytes = readImage(directory, "DALYTRAN");
            return new DailyFile(splitImage(bytes, Transaction.LENGTH));
        }

        char[] read() {
            if (!open) {
                status = "47";
                return null;
            }
            if (eof) {
                status = "46";
                return null;
            }
            if (next == records.size()) {
                eof = true;
                status = "10";
                return null;
            }

            char[] result = records.get(next++);
            if (result.length != Transaction.LENGTH) {
                status = "04";
                return null;
            }
            if (!transportCharacters(result)) {
                status = "30";
                return null;
            }

            status = "00";
            return result.clone();
        }

        String close() {
            if (!open) {
                return status = "42";
            }
            open = false;
            return status = "00";
        }
    }

    private enum Mode {
        INPUT, OUTPUT, IO
    }

    private static final class IndexedFile {
        private final TreeMap<String, char[]> records =
                new TreeMap<>(KEY_ORDER);
        private final int keyLength;
        private final Mode mode;
        private Sink sink;
        private boolean open = true;
        private String status = "00";

        private IndexedFile(int keyLength, Mode mode) {
            this.keyLength = keyLength;
            this.mode = mode;
        }

        static IndexedFile openOutput(Path directory,
                                      String name,
                                      int width,
                                      int keyLength)
                throws FileStatusException {
            IndexedFile file = new IndexedFile(keyLength, Mode.OUTPUT);
            file.sink = Sink.open(directory, name, width);
            return file;
        }

        static IndexedFile openExisting(Path input,
                                        Path output,
                                        String name,
                                        int width,
                                        int keyLength,
                                        boolean update)
                throws FileStatusException {
            IndexedFile file = new IndexedFile(
                    keyLength, update ? Mode.IO : Mode.INPUT);
            List<char[]> image = splitImage(readImage(input, name), width);

            for (char[] record : image) {
                if (record.length != width || !transportCharacters(record)) {
                    throw new FileStatusException("39");
                }
                String key = new String(record, 0, keyLength);
                if (file.records.putIfAbsent(key, record.clone()) != null) {
                    // A transport with duplicate primary keys is not a KSDS.
                    throw new FileStatusException("39");
                }
            }

            if (update) {
                file.sink = Sink.open(output, name, width);
                file.sink.replace(file.records.values());
                if (!"00".equals(file.sink.status)) {
                    file.sink.close();
                    throw new FileStatusException("30");
                }
            }
            return file;
        }

        char[] read(String key) {
            if (!open || mode == Mode.OUTPUT) {
                status = "47";
                return null;
            }
            char[] record = records.get(key);
            if (record == null) {
                status = "23";
                return null;
            }
            status = "00";
            return record.clone();
        }

        void write(char[] record) {
            if (!open || mode == Mode.INPUT) {
                status = "48";
                return;
            }
            String key = new String(record, 0, keyLength);
            if (records.containsKey(key)) {
                status = "22";
                return;
            }
            records.put(key, record.clone());
            sink.replace(records.values());
            status = sink.status;
        }

        void rewrite(char[] record) {
            if (!open || mode != Mode.IO) {
                status = "49";
                return;
            }
            String key = new String(record, 0, keyLength);
            if (!records.containsKey(key)) {
                status = "23";
                return;
            }
            records.put(key, record.clone());
            sink.replace(records.values());
            status = sink.status;
        }

        String close() {
            if (!open) {
                return status = "42";
            }
            open = false;
            return status = sink == null ? "00" : sink.close();
        }
    }

    /**
     * Write-only transport images. No output file is read.
     * Indexed snapshots are emitted in mainframe primary-key collation.
     */
    private static final class Sink {
        private final List<SeekableByteChannel> channels = new ArrayList<>();
        private final int width;
        private boolean open = true;
        private String status = "00";

        private Sink(int width) {
            this.width = width;
        }

        static Sink open(Path directory, String name, int width)
                throws FileStatusException {
            Sink sink = new Sink(width);
            try {
                for (String suffix : List.of("", ".txt", ".bin")) {
                    sink.channels.add(Files.newByteChannel(
                            directory.resolve(name + suffix),
                            StandardOpenOption.WRITE,
                            StandardOpenOption.CREATE_NEW,
                            LinkOption.NOFOLLOW_LINKS));
                }
                return sink;
            } catch (IOException | SecurityException ex) {
                sink.close();
                throw new FileStatusException(statusFor(ex));
            }
        }

        void append(char[] record) {
            if (!open) {
                status = "48";
                return;
            }
            try {
                byte[] bytes = transportRecord(record, width);
                for (SeekableByteChannel channel : channels) {
                    writeFully(channel, ByteBuffer.wrap(bytes));
                }
                status = "00";
            } catch (IOException | SecurityException ex) {
                status = "30";
            }
        }

        void replace(Collection<char[]> records) {
            if (!open) {
                status = "48";
                return;
            }
            try {
                ByteArrayOutputStream image = new ByteArrayOutputStream();
                for (char[] record : records) {
                    image.writeBytes(transportRecord(record, width));
                }
                byte[] bytes = image.toByteArray();

                for (SeekableByteChannel channel : channels) {
                    channel.position(0);
                    writeFully(channel, ByteBuffer.wrap(bytes));
                    channel.truncate(bytes.length);
                }
                status = "00";
            } catch (IOException | SecurityException ex) {
                status = "30";
            }
        }

        String close() {
            if (!open) {
                return status = "42";
            }
            open = false;
            String result = "00";
            for (SeekableByteChannel channel : channels) {
                try {
                    channel.close();
                } catch (IOException ex) {
                    result = "30";
                }
            }
            return status = result;
        }
    }

    /*
     * Input access is limited to the five logical input images, with fixed
     * suffix alternatives. No directory scanning or ancillary file reads.
     */
    private static byte[] readImage(Path directory, String name)
            throws FileStatusException {
        for (String suffix : List.of("", ".txt", ".bin")) {
            Path path = directory.resolve(name + suffix);
            try (SeekableByteChannel channel = Files.newByteChannel(
                    path, StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS)) {
                ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                ByteBuffer buffer = ByteBuffer.allocate(8192);
                while (true) {
                    int count = channel.read(buffer);
                    if (count < 0) {
                        break;
                    }
                    if (count != 0) {
                        bytes.write(buffer.array(), 0, count);
                    }
                    buffer.clear();
                }
                return unwrapHex(bytes.toByteArray());
            } catch (NoSuchFileException ex) {
                // Try the next spelling of the same logical image.
            } catch (IOException | SecurityException ex) {
                throw new FileStatusException(statusFor(ex));
            }
        }
        throw new FileStatusException("35");
    }

    private static void readOptionalImage(Path directory, String name)
            throws FileStatusException {
        try {
            readImage(directory, name);
        } catch (FileStatusException ex) {
            /*
             * OPEN OUTPUT can create a missing file. Missing TRANFILE is
             * therefore not an input-open failure in the source program.
             */
            if (!"35".equals(ex.status)) {
                throw ex;
            }
        }
    }

    private static byte[] unwrapHex(byte[] input) throws FileStatusException {
        byte[] marker =
                "PUBLIC FIXED BYTES HEX".getBytes(StandardCharsets.US_ASCII);
        if (input.length < marker.length) {
            return input;
        }
        for (int i = 0; i < marker.length; i++) {
            if (input[i] != marker[i]) {
                return input;
            }
        }

        ByteArrayOutputStream decoded = new ByteArrayOutputStream();
        int high = -1;
        for (int i = marker.length; i < input.length; i++) {
            int c = input[i] & 0xff;
            if (c == ' ' || c == '\t' || c == '\r' || c == '\n') {
                continue;
            }
            int digit;
            if (c >= '0' && c <= '9') {
                digit = c - '0';
            } else if (c >= 'a' && c <= 'f') {
                digit = c - 'a' + 10;
            } else if (c >= 'A' && c <= 'F') {
                digit = c - 'A' + 10;
            } else {
                throw new FileStatusException("39");
            }
            if (high < 0) {
                high = digit;
            } else {
                decoded.write((high << 4) | digit);
                high = -1;
            }
        }
        if (high >= 0) {
            throw new FileStatusException("39");
        }
        return decoded.toByteArray();
    }

    private static List<char[]> splitImage(byte[] bytes, int width) {
        List<char[]> records = new ArrayList<>();
        if (bytes.length == 0) {
            return records;
        }

        boolean ebcdic = false;
        boolean separators = false;
        for (byte value : bytes) {
            int c = value & 0xff;
            ebcdic |= c >= 128;
            separators |= c == '\r' || c == '\n';
        }

        if (ebcdic || !separators) {
            Charset charset = ebcdic ? IBM037 : StandardCharsets.US_ASCII;
            for (int position = 0; position < bytes.length; position += width) {
                int count = Math.min(width, bytes.length - position);
                records.add(new String(bytes, position, count, charset)
                        .toCharArray());
            }
            return records;
        }

        int start = 0;
        for (int i = 0; i < bytes.length; i++) {
            if (bytes[i] == '\n' || bytes[i] == '\r') {
                records.add(new String(
                        bytes, start, i - start, StandardCharsets.US_ASCII)
                        .toCharArray());
                if (bytes[i] == '\r'
                        && i + 1 < bytes.length
                        && bytes[i + 1] == '\n') {
                    i++;
                }
                start = i + 1;
            }
        }
        if (start < bytes.length) {
            records.add(new String(
                    bytes, start, bytes.length - start,
                    StandardCharsets.US_ASCII).toCharArray());
        }
        return records;
    }

    private static boolean transportCharacters(char[] record) {
        for (char c : record) {
            if (c > 127 || c == '\r' || c == '\n') {
                return false;
            }
        }
        return true;
    }

    private static byte[] transportRecord(char[] record, int width)
            throws IOException {
        if (record.length != width || !transportCharacters(record)) {
            throw new IOException("Invalid fixed-width ASCII record");
        }
        byte[] result = new byte[width + 1];
        for (int i = 0; i < width; i++) {
            result[i] = (byte) record[i];
        }
        result[width] = '\n';
        return result;
    }

    private static void writeFully(SeekableByteChannel channel,
                                   ByteBuffer buffer) throws IOException {
        while (buffer.hasRemaining()) {
            channel.write(buffer);
        }
    }

    private static void writeNew(Path path, byte[] bytes) throws IOException {
        OpenOption[] options = {
                StandardOpenOption.WRITE,
                StandardOpenOption.CREATE_NEW,
                LinkOption.NOFOLLOW_LINKS
        };
        try (SeekableByteChannel channel = Files.newByteChannel(path, options)) {
            writeFully(channel, ByteBuffer.wrap(bytes));
        }
    }

    /*
     * Signed zoned decimal, trailing embedded sign:
     *   C0..C9 -> {ABCDEFGHI
     *   D0..D9 -> }JKLMNOPQR
     * Unsigned F-zone trailing digits are accepted as positive.
     */
    private static long zoned(char[] record, Field field) {
        int last = field.offset() + field.length() - 1;
        long value = 0;
        for (int i = field.offset(); i < last; i++) {
            char c = record[i];
            if (c < '0' || c > '9') {
                throw new DecimalDataException(field.offset());
            }
            value = value * 10 + c - '0';
        }

        char c = record[last];
        int digit;
        boolean negative = false;
        if (c >= '0' && c <= '9') {
            digit = c - '0';
        } else {
            digit = "{ABCDEFGHI".indexOf(c);
            if (digit < 0) {
                digit = "}JKLMNOPQR".indexOf(c);
                negative = true;
            }
            if (digit < 0) {
                throw new DecimalDataException(field.offset());
            }
        }

        value = value * 10 + digit;
        return negative ? -value : value;
    }

    private static void putZoned(char[] record, Field field, long cents) {
        boolean negative = cents < 0;
        long magnitude = Math.abs(cents) % powerOfTen(field.length());

        for (int i = field.offset() + field.length() - 1;
             i >= field.offset(); i--) {
            record[i] = (char) ('0' + magnitude % 10);
            magnitude /= 10;
        }

        int last = field.offset() + field.length() - 1;
        int digit = record[last] - '0';
        record[last] = (negative ? "}JKLMNOPQR" : "{ABCDEFGHI").charAt(digit);
    }

    private static long truncate(long value, int digits) {
        // Java remainder truncates toward zero, retaining the result's sign.
        return value % powerOfTen(digits);
    }

    private static long powerOfTen(int digits) {
        long result = 1;
        for (int i = 0; i < digits; i++) {
            result *= 10;
        }
        return result;
    }

    private static String unsigned(long value, int width) {
        String digits = Long.toString(value % powerOfTen(width));
        return "0".repeat(width - digits.length()) + digits;
    }

    private static char[] spaces(int length) {
        char[] record = new char[length];
        Arrays.fill(record, ' ');
        return record;
    }

    private static String text(char[] record, Field field) {
        return new String(record, field.offset(), field.length());
    }

    private static void move(char[] source, Field from,
                             char[] destination, Field to) {
        int count = Math.min(from.length(), to.length());
        System.arraycopy(source, from.offset(), destination, to.offset(), count);
        Arrays.fill(destination, to.offset() + count,
                to.offset() + to.length(), ' ');
    }

    private static void putText(char[] record, Field field, String value) {
        Arrays.fill(record, field.offset(),
                field.offset() + field.length(), ' ');
        int count = Math.min(value.length(), field.length());
        value.getChars(0, count, record, field.offset());
    }

    private static void zero(char[] record, Field field) {
        Arrays.fill(record, field.offset(),
                field.offset() + field.length(), '0');
    }

    private static char[] initialXref() {
        char[] record = spaces(Xref.LENGTH);
        zero(record, Xref.CUSTOMER_ID);
        zero(record, Xref.ACCOUNT_ID);
        return record;
    }

    private static char[] initialAccount() {
        char[] record = spaces(Account.LENGTH);
        zero(record, Account.ID);
        for (Field field : new Field[]{
                Account.CURRENT_BALANCE, Account.CREDIT_LIMIT,
                Account.CASH_CREDIT_LIMIT, Account.CYCLE_CREDIT,
                Account.CYCLE_DEBIT
        }) {
            putZoned(record, field, 0);
        }
        return record;
    }

    private static char[] initialTransaction() {
        char[] record = spaces(Transaction.LENGTH);
        zero(record, Transaction.CATEGORY_CODE);
        zero(record, Transaction.MERCHANT_ID);
        putZoned(record, Transaction.AMOUNT, 0);
        return record;
    }

    private static char[] initialCategory() {
        char[] record = spaces(Category.LENGTH);
        initializeCategoryNamedFields(record);
        return record;
    }

    private static void initializeCategoryNamedFields(char[] record) {
        zero(record, Category.ACCOUNT_ID);
        putText(record, Category.TYPE_CODE, "");
        zero(record, Category.CATEGORY_CODE);
        putZoned(record, Category.BALANCE, 0);
    }

    private static int[] makeEbcdicOrder() {
        int[] order = new int[128];
        for (int i = 0; i < order.length; i++) {
            byte[] encoded = String.valueOf((char) i).getBytes(IBM037);
            order[i] = encoded[0] & 0xff;
        }
        return order;
    }

    /*
     * CURRENT_DATE accepts:
     *   YYYY-MM-DD
     *   YYYYMMDD
     *   COBOL YYYYMMDDhhmmsscc[+/-hhmm]
     *   ISO local/offset timestamps
     *   DB2 yyyy-MM-dd-HH.mm.ss.ffffff
     *
     * A date without time denotes midnight. An explicit offset is not used
     * to shift the wall-clock fields: COBOL-TS likewise ignores COB-REST.
     * Only the first two fractional digits survive the source's DB2 move.
     */
    private static String scenarioTimestamp(String supplied) {
        Pattern compact = Pattern.compile(
                "([0-9]{4})([0-9]{2})([0-9]{2})"
                + "(?:([0-9]{2})([0-9]{2})([0-9]{2})([0-9]{2})?)?"
                + "(?:[+-][0-9]{4})?");
        Pattern formatted = Pattern.compile(
                "([0-9]{4})-([0-9]{2})-([0-9]{2})"
                + "(?:[T -]([0-9]{2})[:.]([0-9]{2})[:.]([0-9]{2})"
                + "(?:\\.([0-9]{1,9}))?)?"
                + "(?:Z|[+-][0-9]{2}:?[0-9]{2})?");

        Matcher match = compact.matcher(supplied);
        if (!match.matches()) {
            match = formatted.matcher(supplied);
            if (!match.matches()) {
                throw new IllegalArgumentException(
                        "expected a declared date or timestamp");
            }
        }

        int year = Integer.parseInt(match.group(1));
        int month = Integer.parseInt(match.group(2));
        int day = Integer.parseInt(match.group(3));
        int hour = match.group(4) == null
                ? 0 : Integer.parseInt(match.group(4));
        int minute = match.group(5) == null
                ? 0 : Integer.parseInt(match.group(5));
        int second = match.group(6) == null
                ? 0 : Integer.parseInt(match.group(6));
        String fraction = match.group(7) == null ? "" : match.group(7);
        int centiseconds = Integer.parseInt((fraction + "00").substring(0, 2));

        try {
            LocalDateTime.of(year, month, day, hour, minute, second,
                    centiseconds * 10_000_000);
        } catch (RuntimeException ex) {
            throw new IllegalArgumentException("invalid calendar fields", ex);
        }

        return String.format(Locale.ROOT,
                "%04d-%02d-%02d-%02d.%02d.%02d.%02d0000",
                year, month, day, hour, minute, second, centiseconds);
    }

    private static boolean invalidKey(String status) {
        return "21".equals(status)
                || "22".equals(status)
                || "23".equals(status)
                || "24".equals(status);
    }

    private static String statusFor(Exception ex) {
        if (ex instanceof NoSuchFileException) {
            return "35";
        }
        if (ex instanceof AccessDeniedException
                || ex instanceof SecurityException
                || ex instanceof FileAlreadyExistsException) {
            return "37";
        }
        return "30";
    }

    private static void require(String message, String status) {
        if (!"00".equals(status)) {
            abort(message, status);
        }
    }

    private static void abort(String message, String status) {
        System.out.println(message);
        displayIoStatus(status);
        System.out.println("ABENDING PROGRAM");
        throw new Abend();
    }

    private static void displayIoStatus(String status) {
        char first = status.charAt(0);
        char second = status.charAt(1);
        boolean numeric = first >= '0' && first <= '9'
                && second >= '0' && second <= '9';

        String four;
        if (!numeric || first == '9') {
            int byteValue = second < 128 ? EBCDIC_ORDER[second] : second & 0xff;
            four = first + unsigned(byteValue, 3);
        } else {
            four = "00" + status;
        }
        System.out.println("FILE STATUS IS: NNNN" + four);
    }

    private static final class FileStatusException extends Exception {
        private static final long serialVersionUID = 1L;
        final String status;

        FileStatusException(String status) {
            super(status);
            this.status = status;
        }
    }

    private static final class DecimalDataException extends RuntimeException {
        private static final long serialVersionUID = 1L;

        DecimalDataException(int offset) {
            super("Invalid signed zoned decimal at record offset " + offset);
        }
    }

    private static final class Abend extends RuntimeException {
        private static final long serialVersionUID = 1L;
    }
}
