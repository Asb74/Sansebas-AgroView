Option Explicit

Dim accessPath, sqlQuery, outputCsvPath, outputLogPath
Dim conn, rs, fso, csvFile, logFile
Dim rowCount, i
Dim providerUsed, openErr

Set fso = CreateObject("Scripting.FileSystemObject")

If WScript.Arguments.Count >= 4 Then
    outputLogPath = WScript.Arguments(3)
Else
    outputLogPath = "export_access_table_error.log"
End If

On Error Resume Next
Dim logDir
logDir = fso.GetParentFolderName(outputLogPath)
If logDir <> "" And Not fso.FolderExists(logDir) Then fso.CreateFolder(logDir)
Set logFile = fso.OpenTextFile(outputLogPath, 2, True)
On Error Goto 0

LogArguments logFile

If WScript.Arguments.Count <> 4 Then
    logFile.WriteLine "ERROR"
    logFile.WriteLine "Mensaje=Número de argumentos inválido. Esperados=4 Recibidos=" & WScript.Arguments.Count
    logFile.WriteLine "SQLRecibida=" & ArgValue(1)
    logFile.Close
    WScript.Echo "ERROR: número de argumentos inválido"
    WScript.Quit 1
End If

accessPath = WScript.Arguments(0)
sqlQuery = WScript.Arguments(1)
outputCsvPath = WScript.Arguments(2)
outputLogPath = WScript.Arguments(3)

rowCount = 0
providerUsed = ""
openErr = ""

On Error Resume Next
Dim outDir
outDir = fso.GetParentFolderName(outputCsvPath)
If outDir <> "" And Not fso.FolderExists(outDir) Then fso.CreateFolder(outDir)
On Error Goto 0

Set conn = CreateObject("ADODB.Connection")

If Not TryOpenWithProvider(conn, "Microsoft.Jet.OLEDB.4.0", accessPath, logFile, openErr) Then
    If Not TryOpenWithProvider(conn, "Microsoft.ACE.OLEDB.12.0", accessPath, logFile, openErr) Then
        If Not TryOpenWithProvider(conn, "Microsoft.ACE.OLEDB.16.0", accessPath, logFile, openErr) Then
            logFile.WriteLine "ERROR"
            logFile.WriteLine "SQL=" & sqlQuery
            logFile.WriteLine "RegistrosExportados=0"
            logFile.WriteLine "Mensaje=No se pudo abrir Access. Falta proveedor Jet/ACE compatible. Prueba ejecutar con cscript 32 bits o instalar Access Database Engine 32 bits. Último error=" & openErr
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
Dim sourceSql
sourceSql = sqlQuery
If UCase(Left(Trim(sqlQuery), 6)) <> "SELECT" Then
    sourceSql = "SELECT * FROM [" & sqlQuery & "]"
End If
logFile.WriteLine "SQL_Ejecutada=" & sourceSql
rs.Open sourceSql, conn, 3, 1
If Err.Number <> 0 Then
    logFile.WriteLine "ERROR"
    logFile.WriteLine "SQL=" & sourceSql
    logFile.WriteLine "RegistrosExportados=0"
    logFile.WriteLine "Err.Number=" & Err.Number
    logFile.WriteLine "Err.Description=" & Err.Description
    LogColumnsFromSql conn, sourceSql, logFile
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
logFile.WriteLine "SQL=" & sourceSql
logFile.WriteLine "RegistrosExportados=" & rowCount
logFile.WriteLine "Mensaje=Exportación completada"
logFile.Close
WScript.Quit 0

Sub LogArguments(ByRef lf)
    Dim idx
    lf.WriteLine "[VBS_EXPORT]"
    lf.WriteLine "arg_count=" & WScript.Arguments.Count
    For idx = 0 To WScript.Arguments.Count - 1
        lf.WriteLine "arg" & idx & "=" & WScript.Arguments(idx)
    Next
    lf.WriteLine "sql_query=" & ArgValue(1)
End Sub

Function ArgValue(idx)
    If WScript.Arguments.Count > idx Then
        ArgValue = WScript.Arguments(idx)
    Else
        ArgValue = ""
    End If
End Function

Sub LogColumnsFromSql(ByRef dbConn, ByVal sourceSql, ByRef lf)
    Dim tableName, colsRs, cols, schemaRs
    tableName = ExtractBracketedTable(sourceSql)
    If tableName = "" Then Exit Sub
    cols = ""
    On Error Resume Next
    Set colsRs = CreateObject("ADODB.Recordset")
    colsRs.Open "SELECT * FROM [" & tableName & "] WHERE 1=0", dbConn, 3, 1
    If Err.Number = 0 Then
        Dim j
        For j = 0 To colsRs.Fields.Count - 1
            If cols <> "" Then cols = cols & ","
            cols = cols & colsRs.Fields(j).Name
        Next
        colsRs.Close
    Else
        Err.Clear
    End If
    On Error Goto 0
    lf.WriteLine "[LEGACY_SCHEMA] table=" & tableName & " columns=[" & cols & "]"
End Sub

Function ExtractBracketedTable(ByVal sqlText)
    Dim re, matches
    Set re = New RegExp
    re.IgnoreCase = True
    re.Global = False
    re.Pattern = "FROM\s+\[([^\]]+)\]"
    Set matches = re.Execute(sqlText)
    If matches.Count > 0 Then
        ExtractBracketedTable = matches(0).SubMatches(0)
    Else
        ExtractBracketedTable = ""
    End If
End Function

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
