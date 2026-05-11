Option Explicit

Dim accessPath, tableName, outputCsvPath, outputLogPath
If WScript.Arguments.Count < 4 Then
    WScript.Echo "ERROR: argumentos insuficientes"
    WScript.Quit 1
End If

accessPath = WScript.Arguments(0)
tableName = WScript.Arguments(1)
outputCsvPath = WScript.Arguments(2)
outputLogPath = WScript.Arguments(3)

Dim conn, rs, fso, csvFile, logFile
Dim rowCount, i
Dim providerUsed, openErr
rowCount = 0
providerUsed = ""
openErr = ""

On Error Resume Next
Set fso = CreateObject("Scripting.FileSystemObject")
Dim outDir
outDir = fso.GetParentFolderName(outputCsvPath)
If outDir <> "" And Not fso.FolderExists(outDir) Then fso.CreateFolder(outDir)
outDir = fso.GetParentFolderName(outputLogPath)
If outDir <> "" And Not fso.FolderExists(outDir) Then fso.CreateFolder(outDir)
On Error Goto 0

Set logFile = fso.OpenTextFile(outputLogPath, 2, True)
Set conn = CreateObject("ADODB.Connection")

If Not TryOpenWithProvider(conn, "Microsoft.Jet.OLEDB.4.0", accessPath, logFile, openErr) Then
    If Not TryOpenWithProvider(conn, "Microsoft.ACE.OLEDB.12.0", accessPath, logFile, openErr) Then
        If Not TryOpenWithProvider(conn, "Microsoft.ACE.OLEDB.16.0", accessPath, logFile, openErr) Then
            logFile.WriteLine "ERROR"
            logFile.WriteLine "Tabla=" & tableName
            logFile.WriteLine "RegistrosExportados=0"
            logFile.WriteLine "Mensaje=No se pudo abrir Access. Falta proveedor Jet/ACE compatible. Prueba ejecutar con cscript 32 bits o instalar Access Database Engine 32 bits."
            logFile.Close
            WScript.Quit 2
        Else
            providerUsed = "Microsoft.ACE.OLEDB.16.0"
        End If
    Else
        providerUsed = "Microsoft.ACE.OLEDB.12.0"
    End If
Else
    providerUsed = "Microsoft.Jet.OLEDB.4.0"
End If

logFile.WriteLine "ProveedorUsado=" & providerUsed

Set rs = CreateObject("ADODB.Recordset")
On Error Resume Next
rs.Open "SELECT * FROM [" & tableName & "]", conn, 3, 1
If Err.Number <> 0 Then
    logFile.WriteLine "ERROR"
    logFile.WriteLine "Tabla=" & tableName
    logFile.WriteLine "RegistrosExportados=0"
    logFile.WriteLine "Mensaje=No se pudo leer tabla: " & Err.Description
    logFile.Close
    conn.Close
    WScript.Quit 3
End If
On Error Goto 0

Set csvFile = fso.OpenTextFile(outputCsvPath, 2, True)

For i = 0 To rs.Fields.Count - 1
    If i > 0 Then csvFile.Write ";"
    csvFile.Write QuoteCsv(CStr(rs.Fields(i).Name))
Next
csvFile.WriteLine ""

Do Until rs.EOF
    For i = 0 To rs.Fields.Count - 1
        If i > 0 Then csvFile.Write ";"
        csvFile.Write QuoteCsv(FieldToText(rs.Fields(i).Value))
    Next
    csvFile.WriteLine ""
    rowCount = rowCount + 1
    rs.MoveNext
Loop

csvFile.Close
rs.Close
conn.Close

logFile.WriteLine "OK"
logFile.WriteLine "Tabla=" & tableName
logFile.WriteLine "RegistrosExportados=" & rowCount
logFile.WriteLine "Mensaje=Exportación completada"
logFile.Close
WScript.Quit 0

Function TryOpenWithProvider(ByRef dbConn, providerName, dbPath, ByRef lf, ByRef errMsg)
    Dim connStr
    connStr = "Provider=" & providerName & ";Data Source=" & dbPath & ";"
    lf.WriteLine "ProveedorProbado=" & providerName

    On Error Resume Next
    dbConn.Open connStr
    If Err.Number <> 0 Then
        lf.WriteLine "ErrorProveedor(" & providerName & ")=" & Err.Description
        errMsg = Err.Description
        Err.Clear
        TryOpenWithProvider = False
    Else
        TryOpenWithProvider = True
    End If
    On Error Goto 0
End Function

Function FieldToText(value)
    If IsNull(value) Then
        FieldToText = ""
    ElseIf IsDate(value) Then
        FieldToText = Year(value) & "-" & Right("0" & Month(value),2) & "-" & Right("0" & Day(value),2) & " " & Right("0" & Hour(value),2) & ":" & Right("0" & Minute(value),2) & ":" & Right("0" & Second(value),2)
    Else
        FieldToText = CStr(value)
    End If
End Function

Function QuoteCsv(text)
    Dim t
    t = Replace(text, Chr(34), Chr(34) & Chr(34))
    QuoteCsv = Chr(34) & t & Chr(34)
End Function
